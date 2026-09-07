from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..capabilities.executor import CapabilityExecutorService
from ..contracts import Event, Health, RuntimeContext, ServiceSpec, ServiceState
from ..evidence.identity import IdentityGroundingService
from ..interfaces.senses import SensoryFusionService
from .analysis import CognitiveAnalysisService
from .commit import ConversationCommitService
from .constellation import CognitiveConstellationService
from .expression import ExpressionService
from .history import ConversationHistoryService
from .language import analyze_language_and_figures
from .reaction import ReactionService


CandidateProvider = Callable[[str], Awaitable[str]]
StreamCandidateProvider = Callable[[str], AsyncIterator[str]]
ResponseGate = Callable[[str, str], Awaitable[str]]
StreamEmitter = Callable[[str, str, bool], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TurnResult:
    correlation_id: str
    response: str
    verified: bool
    streamed: bool = False


class ConversationSpine:
    spec = ServiceSpec(
        "conversation.spine",
        required=True,
        dependencies=(
            "conversation.history",
            "conversation.analysis",
            "conversation.constellation",
            "conversation.expression",
            "conversation.reaction",
            "conversation.commit",
            "capabilities.executor",
            "learning.experience",
            "evidence.gate",
            "evidence.identity",
            "evidence.web",
            "interfaces.senses",
            "reasoning.provider",
        ),
        start_timeout_seconds=30.0,
    )

    def __init__(
        self,
        candidate: CandidateProvider,
        gate: ResponseGate,
        *,
        stream_candidate: StreamCandidateProvider | None = None,
        shadow_mode: bool = True,
    ) -> None:
        self._candidate = candidate
        owner = getattr(candidate, "__self__", None)
        if stream_candidate is None:
            discovered = getattr(owner, "stream_candidate", None) if owner is not None else None
            if callable(discovered) and bool(getattr(owner, "streaming_available", False)):
                stream_candidate = discovered
        self._stream_candidate = stream_candidate
        self._stream_emitter: StreamEmitter | None = None
        self._gate = gate
        self._shadow_mode = bool(shadow_mode)
        self._context: RuntimeContext | None = None
        self._state = ServiceState.DECLARED
        self._turn_lock = asyncio.Lock()

    async def start(self, context: RuntimeContext) -> None:
        self._context = context
        self._state = ServiceState.READY

    async def stop(self) -> None:
        self._stream_emitter = None
        self._state = ServiceState.STOPPED
        self._context = None

    async def health(self) -> Health:
        mode = "stream_capable" if self._stream_candidate is not None else "full_response"
        lock_state = "turn_busy" if self._turn_lock.locked() else "turn_idle"
        return Health(self._state, f"{mode};{lock_state}")

    def set_stream_emitter(self, emitter: StreamEmitter | None) -> None:
        self._stream_emitter = emitter

    @staticmethod
    def _completed_prefix(text: str) -> str:
        matches = list(re.finditer(r"[.!?](?:[\"')\]]*)?(?=\s|$)", text))
        if not matches:
            return ""
        return text[: matches[-1].end()].strip()

    @staticmethod
    def _streaming_allowed(profile) -> tuple[bool, str]:
        if str(getattr(profile, "depth", "")).casefold() == "deep":
            return False, "deep_reasoning"
        if bool(getattr(profile, "self_system", False)):
            return False, "self_system_truth"
        if bool(getattr(profile, "risk_sensitive", False)):
            return False, "risk_sensitive"
        if bool(getattr(profile, "external_evidence", False)):
            return False, "external_evidence"
        if bool(getattr(profile, "uncertainty_required", False)):
            return False, "uncertainty_required"
        domains = {str(x).casefold() for x in tuple(getattr(profile, "domains", ()) or ())}
        if "medical_science" in domains:
            return False, "medical_science"
        return True, "ordinary_verified_turn"

    async def _identity_checked(self, clean: str, candidate: str, correlation_id: str) -> str:
        if self._context is None:
            raise RuntimeError("conversation_spine_not_ready")
        response = (await self._gate(clean, candidate)).strip()
        if not response:
            raise RuntimeError("verified_response_empty")
        identity = self._context.get_service("evidence.identity")
        if not isinstance(identity, IdentityGroundingService):
            raise RuntimeError("canonical_identity_grounding_missing")
        review = await identity.review_and_publish(response, correlation_id)
        if not review.ok:
            raise RuntimeError("identity_grounding_rejected:" + ",".join(review.violations))
        return response

    async def _commit_fast_answer(
        self,
        *,
        clean: str,
        correlation_id: str,
        profile,
        capability_result,
    ) -> TurnResult:
        if self._context is None:
            raise RuntimeError("conversation_spine_not_ready")
        raw = str(capability_result.payload.get("direct_answer") or "").strip()
        if not raw or capability_result.payload.get("authoritative") is not True:
            raise RuntimeError("fast_answer_contract_invalid")
        response = await self._identity_checked(clean, raw, correlation_id)
        capability_ids = (capability_result.id,)
        active = set(profile.active_nodes) | {
            "conversation.history", "conversation.analysis", "conversation.commit",
            "capabilities.executor", "evidence.gate", "evidence.identity",
            f"tool.{capability_result.id}",
        }
        await self._context.publish(Event("conversation.response.verified", {
            "characters": len(response), "analysis_depth": profile.depth,
            "active_nodes": list(tuple(sorted(active))), "perspective_count": 0,
            "disagreement_axis_count": 0, "expression_style": "fast_local_fact",
            "reaction_mode": "direct", "reaction_intensity": 0.0,
            "history_turns_used": 0, "capability_results": 1,
            "capability_ids": list(capability_ids), "fast_path": True,
            "streamed": False,
            "fast_path_source": str(capability_result.payload.get("source") or "native_capability")[:300],
        }, correlation_id))
        commit = self._context.get_service("conversation.commit")
        if not isinstance(commit, ConversationCommitService):
            raise RuntimeError("canonical_conversation_commit_missing")
        await commit.commit(clean, response, correlation_id, active_nodes=tuple(sorted(active)), capability_ids=capability_ids)
        return TurnResult(correlation_id, response, True, False)

    async def _generate_verified(
        self,
        prompt: str,
        *,
        clean: str,
        correlation_id: str,
        allow_stream: bool,
    ) -> tuple[str, bool, tuple[str, ...]]:
        emitter = self._stream_emitter
        if not allow_stream or emitter is None or self._stream_candidate is None or self._shadow_mode:
            candidate = await self._candidate(prompt)
            return await self._identity_checked(clean, candidate, correlation_id), False, ()

        candidate_buffer = ""
        verified_prefix = ""
        considered_prefix = ""
        buffered_deltas: list[str] = []

        async for fragment in self._stream_candidate(prompt):
            candidate_buffer += str(fragment or "")
            complete = self._completed_prefix(candidate_buffer)
            if not complete or complete == considered_prefix:
                continue
            considered_prefix = complete
            next_verified = await self._identity_checked(clean, complete, correlation_id)
            if verified_prefix and not next_verified.startswith(verified_prefix):
                raise RuntimeError("stream_verifier_rewrote_committed_prefix")
            delta = next_verified[len(verified_prefix):]
            if delta:
                buffered_deltas.append(delta)
            verified_prefix = next_verified
            if self._context is not None:
                await self._context.publish(Event("conversation.response.stream_chunk_verified", {
                    "committed_characters": len(verified_prefix),
                    "delta_characters": len(delta),
                    "outward_delivered": False,
                    "awaiting_atomic_acceptance": True,
                }, correlation_id))

        candidate = candidate_buffer.strip()
        if not candidate:
            raise RuntimeError("candidate_stream_empty")
        response = await self._identity_checked(clean, candidate, correlation_id)
        if verified_prefix and not response.startswith(verified_prefix):
            raise RuntimeError("stream_final_verification_rewrote_committed_prefix")
        final_delta = response[len(verified_prefix):]
        if final_delta:
            buffered_deltas.append(final_delta)
        return response, bool(buffered_deltas or verified_prefix), tuple(buffered_deltas)

    async def _deliver_committed_stream(
        self,
        correlation_id: str,
        response: str,
        deltas: tuple[str, ...],
    ) -> None:
        emitter = self._stream_emitter
        if emitter is None:
            raise RuntimeError("committed_stream_emitter_unavailable")
        if not deltas:
            await emitter(correlation_id, response, True)
            return
        for index, delta in enumerate(deltas):
            await emitter(correlation_id, delta, index == len(deltas) - 1)

    async def respond(self, text: str, correlation_id: str) -> TurnResult:
        if self._state != ServiceState.READY or self._context is None:
            raise RuntimeError("conversation_spine_not_ready")
        async with self._turn_lock:
            if self._state != ServiceState.READY or self._context is None:
                raise RuntimeError("conversation_spine_not_ready")
            return await self._respond_transaction(text, correlation_id)

    async def _respond_transaction(self, text: str, correlation_id: str) -> TurnResult:
        clean = str(text or "").strip()
        if not clean:
            raise ValueError("empty_input")
        if self._context is None:
            raise RuntimeError("conversation_spine_not_ready")
        await self._context.publish(Event("conversation.input.accepted", {"characters": len(clean)}, correlation_id))

        history = self._context.get_service("conversation.history")
        if not isinstance(history, ConversationHistoryService):
            raise RuntimeError("canonical_conversation_history_missing")
        history_rows = history.relevant(clean, limit=4)
        history_context = history.cognition_context(clean, limit=4)
        if history_context:
            await self._context.publish(Event("conversation.history.context", {
                "characters": len(history_context), "turns": len(history_rows),
            }, correlation_id))

        analysis = self._context.get_service("conversation.analysis")
        if not isinstance(analysis, CognitiveAnalysisService):
            raise RuntimeError("canonical_cognitive_analysis_missing")
        profile = await analysis.analyze(clean, correlation_id)
        language_profile = analyze_language_and_figures(clean)
        await self._context.publish(Event(
            "conversation.language_and_figures.analyzed",
            language_profile.as_dict(), correlation_id,
        ))

        capabilities = self._context.get_service("capabilities.executor")
        if not isinstance(capabilities, CapabilityExecutorService):
            raise RuntimeError("canonical_capability_executor_missing")
        capability_results = await capabilities.execute_for_turn(
            clean, requested=profile.requested_capabilities,
            correlation_id=correlation_id, shadow_mode=self._shadow_mode,
        )
        capability_context = capabilities.cognition_context(capability_results)
        fast_result = next((r for r in capability_results if r.ok and r.payload.get("authoritative") is True and str(r.payload.get("direct_answer") or "").strip()), None)
        if fast_result is not None:
            return await self._commit_fast_answer(
                clean=clean, correlation_id=correlation_id,
                profile=profile, capability_result=fast_result,
            )

        senses = self._context.get_service("interfaces.senses")
        if not isinstance(senses, SensoryFusionService):
            raise RuntimeError("canonical_sensory_fusion_missing")
        sensory_rows = senses.recent(window_seconds=20.0, limit=12)
        sensory_context = senses.cognition_context(window_seconds=20.0, limit=12)
        sensory_modalities = tuple(sorted({row.modality for row in sensory_rows}))
        if sensory_context:
            await self._context.publish(Event("conversation.sensory.context", {
                "observation_count": len(sensory_rows),
                "modalities": list(sensory_modalities),
                "raw_media_retained": False,
                "single_generation_authority": True,
            }, correlation_id))

        constellation = self._context.get_service("conversation.constellation")
        expression = self._context.get_service("conversation.expression")
        reaction = self._context.get_service("conversation.reaction")
        if not isinstance(constellation, CognitiveConstellationService):
            raise RuntimeError("canonical_cognitive_constellation_missing")
        if not isinstance(expression, ExpressionService):
            raise RuntimeError("canonical_expression_service_missing")
        if not isinstance(reaction, ReactionService):
            raise RuntimeError("canonical_reaction_service_missing")

        await self._context.publish(Event("conversation.web_evidence.analysis", {
            "mode": profile.web_decision.mode, "needed": profile.external_evidence,
            "reasons": list(profile.web_decision.reasons),
        }, correlation_id))

        async def research_web() -> tuple[str, int, str | None]:
            if not profile.external_evidence:
                return "", 0, None
            web = self._context.get_service("evidence.web")
            bundle = await web.research(clean)
            context = web.cognition_context(bundle)
            await self._context.publish(Event(
                "conversation.web_evidence.ready" if bundle.ok else "conversation.web_evidence.unavailable",
                {"source_count": len(bundle.sources), "error": bundle.error}, correlation_id,
            ))
            return context, len(bundle.sources), bundle.error

        plan, expression_profile, reaction_profile, web_result = await asyncio.gather(
            constellation.plan(profile, correlation_id),
            expression.select(profile, correlation_id),
            reaction.select(clean, profile, correlation_id),
            research_web(),
        )
        web_context, web_source_count, web_error = web_result
        fanout_roads = [
            "conversation.constellation",
            "conversation.expression",
            "conversation.reaction",
        ]
        if profile.external_evidence:
            fanout_roads.append("evidence.web")
        await self._context.publish(Event("conversation.neural_fanout.completed", {
            "roads": fanout_roads,
            "road_count": len(fanout_roads),
            "concurrent": len(fanout_roads) > 1,
            "single_generation_authority": True,
        }, correlation_id))

        learning = self._context.get_service("learning.experience")
        context_builder = getattr(learning, "cognition_context", None)
        learned_context = context_builder() if callable(context_builder) else ""
        identity = self._context.get_service("evidence.identity")
        if not isinstance(identity, IdentityGroundingService):
            raise RuntimeError("canonical_identity_grounding_missing")

        capability_ids = tuple(r.id for r in capability_results)
        fusion_roads = list(fanout_roads)
        if capability_results:
            fusion_roads.append("capabilities.executor")
        if sensory_context:
            fusion_roads.append("interfaces.senses")
        if history_context:
            fusion_roads.append("conversation.history")
        if learned_context:
            fusion_roads.append("learning.experience")
        fusion_context = "\n".join((
            "<eira_fusion_receipt>",
            "roads=" + ",".join(fusion_roads),
            f"perspective_receipts={len(plan.receipts)}",
            "disagreement_axes=" + ",".join(plan.disagreement_axes or ("none",)),
            "capability_ids=" + ",".join(capability_ids or ("none",)),
            f"sensory_observations={len(sensory_rows)}",
            "sensory_modalities=" + ",".join(sensory_modalities or ("none",)),
            f"web_source_count={web_source_count}",
            f"web_error={web_error or 'none'}",
            f"accepted_history_turns={len(history_rows)}",
            f"learning_context={str(bool(learned_context)).lower()}",
            "single_generation_authority=true",
            "accepted_state_authority=conversation.commit",
            "Instruction: fuse all available road and sensory evidence into one coherent answer; preserve material disagreements, provenance, and uncertainty rather than averaging them away.",
            "</eira_fusion_receipt>",
        ))
        await self._context.publish(Event("conversation.cognition.fused", {
            "roads": fusion_roads,
            "perspective_receipt_count": len(plan.receipts),
            "disagreement_axes": list(plan.disagreement_axes),
            "capability_ids": list(capability_ids),
            "sensory_observation_count": len(sensory_rows),
            "sensory_modalities": list(sensory_modalities),
            "web_source_count": web_source_count,
            "web_error": web_error,
            "history_turns_used": len(history_rows),
            "learning_context": bool(learned_context),
            "single_generation_authority": True,
            "accepted_state_authority": "conversation.commit",
        }, correlation_id))

        context_parts = [clean]
        if history_context:
            context_parts.append(history_context)
        context_parts.extend([
            profile.cognition_context(), language_profile.cognition_context(),
            plan.cognition_context(), expression_profile.cognition_context(),
            reaction_profile.cognition_context(), identity.cognition_context(self_system=profile.self_system),
            fusion_context,
        ])
        if capability_context:
            context_parts.append(capability_context)
        if sensory_context:
            context_parts.append(sensory_context)
        if learned_context:
            context_parts.append(learned_context)
            await self._context.publish(Event("conversation.experience.context", {"characters": len(learned_context)}, correlation_id))
        if web_context:
            context_parts.append(web_context)

        allow_stream, stream_reason = self._streaming_allowed(profile)
        await self._context.publish(Event("conversation.response.streaming_policy", {
            "allowed": allow_stream, "reason": stream_reason, "depth": profile.depth,
        }, correlation_id))
        response, streamed, stream_deltas = await self._generate_verified(
            "\n\n".join(context_parts), clean=clean,
            correlation_id=correlation_id, allow_stream=allow_stream,
        )
        active = set(profile.active_nodes) | set(plan.active_nodes) | {
            "conversation.history", "conversation.expression", "conversation.reaction", "capabilities.executor",
        } | {f"tool.{r.id}" for r in capability_results}
        if sensory_context:
            active.add("interfaces.senses")
        if profile.external_evidence:
            active.add("evidence.web")
        await self._context.publish(Event("conversation.response.verified", {
            "characters": len(response), "analysis_depth": profile.depth,
            "active_nodes": list(tuple(sorted(active))), "perspective_count": len(plan.perspectives),
            "perspective_receipt_count": len(plan.receipts),
            "disagreement_axis_count": len(plan.disagreement_axes), "expression_style": expression_profile.style,
            "reaction_mode": reaction_profile.mode, "reaction_intensity": reaction_profile.intensity,
            "history_turns_used": len(history_rows), "capability_results": len(capability_results),
            "capability_ids": list(capability_ids), "fast_path": False, "streamed": streamed,
            "sensory_observation_count": len(sensory_rows),
            "sensory_modalities": list(sensory_modalities),
            "streaming_policy": stream_reason,
            "requested_language": language_profile.requested_language_code,
            "figurative_modes": [
                name for name, enabled in (("analogy", language_profile.analogy), ("metaphor", language_profile.metaphor), ("poetry", language_profile.poetry)) if enabled
            ],
        }, correlation_id))

        commit = self._context.get_service("conversation.commit")
        if not isinstance(commit, ConversationCommitService):
            raise RuntimeError("canonical_conversation_commit_missing")
        await commit.commit(
            clean, response, correlation_id,
            active_nodes=tuple(sorted(active)), capability_ids=capability_ids,
        )
        if streamed:
            await self._deliver_committed_stream(correlation_id, response, stream_deltas)
            await self._context.publish(Event("conversation.response.stream_released", {
                "chunks": len(stream_deltas),
                "characters": len(response),
                "accepted_state_committed": True,
            }, correlation_id))
        return TurnResult(correlation_id, response, True, streamed)
