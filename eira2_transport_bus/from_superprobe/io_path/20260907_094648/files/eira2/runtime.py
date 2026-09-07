from __future__ import annotations

import asyncio
from pathlib import Path

from .capabilities.engineering import VerifiedEngineeringService
from .capabilities.executor import CapabilityExecutorService
from .capabilities.workers import ExternalWorkerService
from .capabilities.worlds import WorldSimulationService
from .config.schema import RuntimeConfig
from .conversation.analysis import CognitiveAnalysisService
from .conversation.commit import ConversationCommitService
from .conversation.constellation import CognitiveConstellationService
from .conversation.expression import ExpressionService
from .conversation.history import ConversationHistoryService
from .conversation.reaction import ReactionService
from .conversation.spine import ConversationSpine, TurnResult
from .delivery.gate import DeliveryGate, Sink
from .delivery.presence import ReactivePresenceService
from .delivery.voice import VoiceOutputService
from .evidence.gate import EvidenceGate, Verifier
from .evidence.identity import IdentityGroundingService
from .evidence.web import WebEvidenceService
from .interfaces.ingress import IngressService, InputKind
from .interfaces.native import NativeInputEvidenceService
from .interfaces.senses import SensoryFusionService
from .kernel.bootstrap import BootstrapService
from .kernel.events import EventService
from .kernel.lock import ProcessLock
from .kernel.supervisor import Supervisor
from .learning.experience import ExperienceLearningService
from .memory.service import MemoryService
from .neural.organism import OrganismNeuralHTTPService
from .operations.coordinator import OperationsCoordinator
from .operations.full_doctor import FullDoctorService
from .operations.health import HealthCoordinator
from .operations.resilience import ResilienceService
from .operations.status import StatusService
from .operations.work import WorkManagementService
from .reasoning.provider import Generate, ReasoningProvider
from .registry.extensions import ExtensionManagerService
from .registry.graph import NodeRecord, NodeRegistryService
from .registry.manifests import discover
from .repair.activation import ActivationService
from .repair.autonomy import AutonomousEvolutionService
from .repair.coordinator import RepairCoordinator
from .repair.evolution import ProposalProvider
from .repair.proposal_provider import StructuredProposalProvider
from .security.attestation import SecurityAttestationService
from .security.jellyfish_platform import PlatformJellyfishImmuneService
from .state.checkpoints import CheckpointService
from .state.store import StateStore


class Eira2Runtime:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        generate: Generate,
        verify: Verifier,
        sinks: list[Sink] | None = None,
        self_build_provider: ProposalProvider | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.project_root = Path(__file__).resolve().parents[1]
        self.supervisor = Supervisor()

        self.lock = ProcessLock(config.root / "var" / "eira2.lock")
        self.events = EventService()
        self.state = StateStore(config.state_path)
        self.checkpoints = CheckpointService(config.root / "var" / "checkpoints")
        self.registry = NodeRegistryService()
        self.capabilities = CapabilityExecutorService()
        self.extensions = ExtensionManagerService(self.project_root)
        self.memory = MemoryService()
        self.history = ConversationHistoryService()
        self.work = WorkManagementService()
        self.learning = ExperienceLearningService()
        self.security_attestation = SecurityAttestationService()
        self.jellyfish_immune = PlatformJellyfishImmuneService()
        self.engineering = VerifiedEngineeringService()
        self.worlds = WorldSimulationService()
        self.workers = ExternalWorkerService()
        self.evidence = EvidenceGate(verify)
        self.web_evidence = WebEvidenceService()
        self.identity = IdentityGroundingService()
        self.analysis = CognitiveAnalysisService()
        self.constellation = CognitiveConstellationService()
        self.expression = ExpressionService()
        self.reaction = ReactionService()
        self.commit = ConversationCommitService()
        self.reasoning = ReasoningProvider(generate)
        self.conversation = ConversationSpine(
            self.reasoning.candidate,
            self.evidence.verify,
            shadow_mode=config.shadow_mode,
        )
        self.presence = ReactivePresenceService()
        self.voice = VoiceOutputService(
            config.root,
            enabled=config.voice_enabled,
            shadow_mode=config.shadow_mode,
        )
        outward_sinks = list(sinks or ())
        turn_sinks = [self.voice.sink_for_turn] if config.voice_enabled else []
        self.delivery = DeliveryGate(
            outward_sinks,
            shadow_mode=config.shadow_mode,
            turn_sinks=turn_sinks,
        )
        self.ingress = IngressService()
        self.native_input = NativeInputEvidenceService()
        self.senses = SensoryFusionService()
        self.neural_ui = (
            OrganismNeuralHTTPService(
                config.root,
                host=config.neural_ui_host,
                port=config.neural_ui_port,
                trace=config.neural_execution_trace,
                sync_interval_seconds=config.neural_sync_interval_seconds,
            )
            if config.neural_ui_enabled
            else None
        )
        self.health = HealthCoordinator()
        self.status_service = StatusService(
            config.root / "var" / "status.json",
            shadow_mode=config.shadow_mode,
        )
        self.doctor = FullDoctorService(self.project_root, config.state_path)
        self.operations = OperationsCoordinator()
        self.resilience = ResilienceService(config.root)
        self.bootstrap = BootstrapService(self.project_root)
        self.activation = ActivationService(
            config.root / "var" / "activation",
            self.project_root,
        )
        self.repair = RepairCoordinator(enabled=config.repair_enabled)
        if self_build_provider is None and config.self_evolution_enabled:
            self_build_provider = StructuredProposalProvider(
                self.project_root,
                self.reasoning.candidate,
            )
        self.self_evolution = AutonomousEvolutionService(
            self.project_root,
            config.root / "var",
            enabled=config.self_evolution_enabled,
            provider=self_build_provider,
            interval_seconds=config.self_evolution_interval_seconds,
        )

        services = [
            self.lock, self.events, self.state, self.checkpoints, self.registry,
            self.capabilities, self.extensions, self.memory, self.history, self.work,
            self.learning, self.security_attestation, self.jellyfish_immune,
            self.engineering, self.worlds, self.workers, self.evidence, self.web_evidence,
            self.identity, self.analysis, self.constellation, self.expression, self.reaction,
            self.commit, self.reasoning, self.conversation, self.presence, self.voice,
            self.delivery, self.ingress, self.native_input, self.senses,
        ]
        if self.neural_ui is not None:
            services.append(self.neural_ui)
        services.extend([
            self.health, self.status_service, self.doctor, self.operations, self.resilience,
            self.bootstrap, self.activation, self.repair, self.self_evolution,
        ])

        manifests = discover(self.project_root / "manifests")
        by_name = {manifest.name: manifest for manifest in manifests}
        capabilities: dict[str, tuple[str, ...]] = {}
        service_names = {service.spec.name for service in services}
        for service in services:
            spec = service.spec
            manifest = by_name.get(spec.name)
            if manifest is None:
                raise RuntimeError(f"runtime_service_manifest_missing:{spec.name}")
            if manifest.required != spec.required:
                raise RuntimeError(f"runtime_manifest_required_mismatch:{spec.name}")
            if tuple(manifest.dependencies) != tuple(spec.dependencies):
                raise RuntimeError(
                    f"runtime_manifest_dependency_mismatch:{spec.name}:"
                    f"manifest={manifest.dependencies}:runtime={spec.dependencies}"
                )
            if float(spec.start_timeout_seconds) > float(manifest.startup_timeout_seconds):
                raise RuntimeError(
                    f"runtime_manifest_startup_timeout_exceeded:{spec.name}:"
                    f"manifest={manifest.startup_timeout_seconds}:runtime={spec.start_timeout_seconds}"
                )
            capabilities[spec.name] = manifest.capabilities

        for manifest in manifests:
            if manifest.required and manifest.name not in service_names:
                raise RuntimeError(f"required_manifest_runtime_service_missing:{manifest.name}")

        self.registry.seed([service.spec for service in services], capabilities=capabilities)
        for service in services:
            self.supervisor.register(service)

    async def start(self) -> None:
        await self.supervisor.start()
        if not self.capabilities.bindings():
            await self.capabilities.install_runtime_introspection_bindings()
        doctor = await asyncio.to_thread(self.doctor.evaluate)
        if not doctor.ok:
            await self.supervisor.stop()
            raise RuntimeError("post_boot_doctor_failed:" + ";".join(doctor.errors[:8]))
        extension_receipt = await self.extensions.attach_all(
            self.supervisor, shadow_mode=self.config.shadow_mode,
        )
        if not extension_receipt.get("ok"):
            await self.supervisor.stop()
            raise RuntimeError(
                "dynamic_extension_reconcile_failed:" + ";".join(extension_receipt.get("errors", ())[:8])
            )
        capability_receipt = await self.capabilities.reconcile_services(self.supervisor)
        if not capability_receipt.get("ok"):
            await self.supervisor.stop()
            raise RuntimeError(
                "capability_reconcile_failed:" + ";".join(capability_receipt.get("errors", ())[:8])
            )
        final_doctor = await asyncio.to_thread(self.doctor.evaluate)
        if not final_doctor.ok:
            await self.supervisor.stop()
            raise RuntimeError("post_reconcile_doctor_failed:" + ";".join(final_doctor.errors[:8]))

    async def stop(self) -> None:
        await self.supervisor.stop()

    async def process(self, text: str, *, kind: InputKind = InputKind.TERMINAL) -> TurnResult:
        envelope = self.ingress.accept(text, kind)
        await self.presence.begin(envelope.correlation_id, mode="thinking")
        try:
            result = await self.conversation.respond(envelope.text, envelope.correlation_id)
            await self.delivery.deliver(result.correlation_id, result.response)
            return result
        finally:
            await self.presence.end(envelope.correlation_id)

    async def record_experience(self, *, lesson_key: str, observation: str, outcome: str, supported: bool, verified: bool, evidence_refs: tuple[str, ...] = (), tags: tuple[str, ...] = ()) -> dict:
        return await self.learning.record(lesson_key=lesson_key, observation=observation, outcome=outcome, supported=supported, verified=verified, evidence_refs=evidence_refs, tags=tags)

    def verified_lessons(self, *, tags: tuple[str, ...] = (), limit: int = 12):
        return self.learning.verified_lessons(tags=tags, limit=limit)

    async def observe_board_temperature(self, zone_id: str, celsius: float, *, sensor_resolution_c: float = 0.01, workload_fraction: float | None = None, at: float | None = None) -> dict:
        return await self.jellyfish_immune.observe_temperature(zone_id, celsius, sensor_resolution_c=sensor_resolution_c, workload_fraction=workload_fraction, at=at)

    async def observe_board_health(self, zone_id: str, *, temperature_c: float, workload_fraction: float | None = None, current_a: float | None = None, voltage_v: float | None = None, power_w: float | None = None, rf_dbm: float | None = None, fan_rpm: float | None = None, peer_temperatures_c: tuple[float, ...] = (), integrity_ok: bool = True, network_anomaly: bool = False, sensor_resolution_c: float = 0.01, at: float | None = None) -> dict:
        return await self.jellyfish_immune.observe_board_state(zone_id, temperature_c=temperature_c, workload_fraction=workload_fraction, current_a=current_a, voltage_v=voltage_v, power_w=power_w, rf_dbm=rf_dbm, fan_rpm=fan_rpm, peer_temperatures_c=peer_temperatures_c, integrity_ok=integrity_ok, network_anomaly=network_anomaly, sensor_resolution_c=sensor_resolution_c, at=at)

    def provision_jellyfish_sentinels(self, targets: tuple[str, ...], *, blueprint_sha256: str, per_target: int = 1) -> tuple[dict, ...]:
        return self.jellyfish_immune.provision_sentinels(targets, blueprint_sha256=blueprint_sha256, per_target=per_target)

    async def observe_security_threat(self, **kwargs) -> dict:
        return await self.jellyfish_immune.observe_threat(**kwargs)

    async def defend_jellyfish(self, unit_id: str, *, threat: dict) -> dict:
        return await self.jellyfish_immune.defend(unit_id, threat=threat)

    def voice_status(self) -> dict[str, object]:
        return self.voice.status()

    def find_nodes(self, query: str) -> tuple[NodeRecord, ...]:
        return self.registry.find(query)

    def find_capabilities(self, query: str = ""):
        return self.capabilities.discover(query)

    async def add_runtime_node(self, name: str, *, kind: str = "runtime_node", capabilities: tuple[str, ...] = ()) -> NodeRecord:
        return await self.registry.register_node(name, kind=kind, capabilities=capabilities)

    async def add_bridge(self, source: str, target: str, *, kind: str = "runtime_call", conductive: bool = True, evidence: str = "runtime_registration"):
        return await self.registry.add_bridge(source, target, kind=kind, conductive=conductive, evidence=evidence)

    def evaluate_self(self) -> dict:
        return self.doctor.evaluate().as_dict()

    def create_checkpoint(self, reason: str) -> dict:
        return self.checkpoints.create(reason=reason)

    async def reconcile_extensions(self) -> dict:
        extension_receipt = await self.extensions.attach_all(self.supervisor, shadow_mode=self.config.shadow_mode)
        capability_receipt = await self.capabilities.reconcile_services(self.supervisor)
        return {"ok": bool(extension_receipt.get("ok")) and bool(capability_receipt.get("ok")), "extensions": extension_receipt, "capabilities": capability_receipt}

    async def maintenance_cycle(self) -> dict:
        return await self.operations.run_once()

    async def autonomous_repair_cycle(self) -> dict:
        return await self.self_evolution.cycle()

    async def build_self(self, instruction: str, *, context_paths: tuple[str, ...] = ()) -> dict:
        if not self.config.self_evolution_enabled:
            raise RuntimeError("self_build_disabled")
        provider = self.self_evolution.provider
        proposer = getattr(provider, "propose_instruction", None)
        if not callable(proposer):
            raise RuntimeError("self_build_instruction_provider_missing")
        proposal = await proposer(instruction, context_paths=context_paths)
        if proposal is None:
            return {"ok": False, "status": "no_safe_proposal"}
        workspace = await asyncio.to_thread(self.self_evolution.stage, proposal)
        receipt = await asyncio.to_thread(self.self_evolution.validate_staged, proposal, workspace)
        if not receipt.accepted:
            return {"ok": False, "status": "candidate_rejected", "proposal_id": proposal.proposal_id, "doctor_ok": receipt.doctor_ok, "tests_ok": receipt.tests_ok, "doctor_errors": list(receipt.doctor_errors)}
        return await self.self_evolution.promote(proposal, safe_boundary=True)


def default_config(root: Path) -> RuntimeConfig:
    root = root.resolve()
    return RuntimeConfig(root=root, state_path=root / "var" / "eira2.sqlite3", shadow_mode=True, terminal_enabled=False, voice_enabled=False, repair_enabled=False, self_evolution_enabled=False, neural_ui_enabled=False)
