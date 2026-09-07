import asyncio
import json
from dataclasses import replace

import pytest

from eira2.runtime import Eira2Runtime, default_config


def _active_config(tmp_path):
    auth = tmp_path / "cutover-test-authorization.json"
    auth.write_text(json.dumps({
        "schema": "eira2_cutover_authorization_v2",
        "accepted": True,
        "functional_preservation_verified": True,
    }), encoding="utf-8")
    return replace(
        default_config(tmp_path),
        shadow_mode=False,
        terminal_enabled=True,
        voice_enabled=False,
        repair_enabled=False,
        self_evolution_enabled=False,
        neural_ui_enabled=False,
        cutover_authorization_path=auth,
    )


def test_verified_stream_is_buffered_until_atomic_acceptance_then_released_in_chunks(tmp_path):
    async def scenario():
        allow_second = asyncio.Event()
        delivered: list[str] = []
        stream_calls = 0
        full_calls = 0

        class Generator:
            async def generate(self, _prompt: str) -> str:
                nonlocal full_calls
                full_calls += 1
                return "full path should not run"

            async def stream(self, _prompt: str):
                nonlocal stream_calls
                stream_calls += 1
                yield "First verified sentence. "
                await allow_second.wait()
                yield "Second verified sentence."

        async def verify(_user: str, candidate: str) -> str:
            return " ".join(candidate.split())

        async def sink(text: str) -> None:
            delivered.append(text)

        generator = Generator()
        runtime = Eira2Runtime(_active_config(tmp_path), generate=generator.generate, verify=verify, sinks=[sink])
        await runtime.start()
        try:
            task = asyncio.create_task(runtime.process("Explain the verified streaming bridge."))
            await asyncio.sleep(0.05)
            assert delivered == []
            assert task.done() is False
            allow_second.set()
            result = await asyncio.wait_for(task, timeout=2.0)
            assert result.verified is True
            assert result.streamed is True
            assert result.response == "First verified sentence. Second verified sentence."
            assert "".join(delivered) == result.response
            assert stream_calls == 1
            assert full_calls == 0
            history = runtime.history.recent()
            assert len(history) == 1
            assert history[0].assistant == result.response
            assert runtime.memory.recall("accepted.last_turn")["atomic_persistence"] is True
            with pytest.raises(RuntimeError, match="duplicate_outward_delivery"):
                await runtime.delivery.deliver(result.correlation_id, result.response)
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_stream_fails_closed_without_speaking_if_verifier_rewrites_buffered_prefix(tmp_path):
    async def scenario():
        delivered: list[str] = []

        class Generator:
            async def generate(self, _prompt: str) -> str:
                return "unused"

            async def stream(self, _prompt: str):
                yield "Keep this first sentence. "
                yield "Then add this second sentence."

        async def verify(_user: str, candidate: str) -> str:
            clean = " ".join(candidate.split())
            if "second sentence" in clean:
                return clean.replace("Keep this first sentence.", "Rewrite the first sentence.")
            return clean

        async def sink(text: str) -> None:
            delivered.append(text)

        generator = Generator()
        runtime = Eira2Runtime(_active_config(tmp_path), generate=generator.generate, verify=verify, sinks=[sink])
        await runtime.start()
        try:
            with pytest.raises(RuntimeError, match="stream_verifier_rewrote_committed_prefix"):
                await runtime.process("Give me a two sentence engineering explanation.")
            assert delivered == []
            assert runtime.history.recent() == ()
            assert runtime.memory.recall("accepted.last_turn") is None
        finally:
            await runtime.stop()

    asyncio.run(scenario())


def test_atomic_commit_failure_blocks_all_buffered_stream_delivery(tmp_path):
    async def scenario():
        delivered: list[str] = []

        class Generator:
            async def generate(self, _prompt: str) -> str:
                return "unused"

            async def stream(self, _prompt: str):
                yield "First safe sentence. "
                yield "Second safe sentence."

        async def verify(_user: str, candidate: str) -> str:
            return " ".join(candidate.split())

        async def sink(text: str) -> None:
            delivered.append(text)

        generator = Generator()
        runtime = Eira2Runtime(_active_config(tmp_path), generate=generator.generate, verify=verify, sinks=[sink])
        await runtime.start()
        original = runtime.memory.remember_many

        def fail_atomic_write(rows):
            raise RuntimeError("injected_atomic_stream_commit_failure")

        runtime.memory.remember_many = fail_atomic_write  # type: ignore[method-assign]
        try:
            with pytest.raises(RuntimeError, match="injected_atomic_stream_commit_failure"):
                await runtime.process("Stream this only after acceptance.")
            assert delivered == []
            assert runtime.history.recent() == ()
            assert runtime.memory.recall("accepted.last_turn") is None
        finally:
            runtime.memory.remember_many = original  # type: ignore[method-assign]
            await runtime.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "prompt",
    [
        "Explain your internal runtime architecture and every service that participated.",
        "Give me medical advice about a dangerous medication dose.",
        "Research the latest external evidence and tell me what is currently true.",
        "Do a deep end-to-end analysis of this uncertain system architecture.",
    ],
)
def test_sensitive_truth_paths_complete_before_any_progressive_delivery(tmp_path, prompt):
    async def scenario():
        delivered: list[str] = []
        stream_calls = 0
        full_calls = 0

        class Generator:
            async def generate(self, _prompt: str) -> str:
                nonlocal full_calls
                full_calls += 1
                return "Fully generated and then verified response."

            async def stream(self, _prompt: str):
                nonlocal stream_calls
                stream_calls += 1
                yield "This must never be spoken early."

        async def verify(_user: str, candidate: str) -> str:
            return candidate

        async def sink(text: str) -> None:
            delivered.append(text)

        generator = Generator()
        runtime = Eira2Runtime(_active_config(tmp_path), generate=generator.generate, verify=verify, sinks=[sink])
        if "latest external evidence" in prompt:
            async def fake_research(_query: str):
                from eira2.evidence.web import EvidenceBundle
                return EvidenceBundle(query=_query, sources=(), error="test_offline")
            runtime.web_evidence.research = fake_research
        await runtime.start()
        try:
            result = await runtime.process(prompt)
            assert result.verified is True
            assert result.streamed is False
            assert stream_calls == 0
            assert full_calls == 1
            assert delivered == ["Fully generated and then verified response."]
        finally:
            await runtime.stop()

    asyncio.run(scenario())
