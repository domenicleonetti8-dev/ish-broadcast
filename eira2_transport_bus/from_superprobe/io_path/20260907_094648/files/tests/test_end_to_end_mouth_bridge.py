import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

from eira2.delivery import voice as voice_module
from eira2.runtime import Eira2Runtime, default_config


def test_full_turn_runs_ingress_tools_reasoning_verification_and_flash_cube_mouth(monkeypatch, tmp_path):
    instances = []

    class FakeBluetoothRuntime:
        def __init__(self):
            self.spoken = []
            self.played_on = []
            self.voice_model = tmp_path / "female.onnx"
            self._default_sink = "bluez_output.AA_BB_CC_DD_EE_FF"
            self._active_sinks = [
                "bluez_output.AA_BB_CC_DD_EE_FF",
                "bluez_output.11_22_33_44_55_66",
            ]
            instances.append(self)

        def ensure(self):
            return {
                "connected_devices": {
                    "AA:BB:CC:DD:EE:FF": "Other Speaker",
                    "11:22:33:44:55:66": "Flash Cube",
                },
                "active_sinks": list(self._active_sinks),
                "default_sink": self._default_sink,
            }

        def speak_now(self, text):
            self.spoken.append(text)
            self.played_on.append(self._default_sink)

        def status(self):
            return self.ensure()

    real_import_module = voice_module.importlib.import_module

    def selective_import(name, *args, **kwargs):
        if name == "extensions.eira_bluetooth_voice_ai.runtime":
            return SimpleNamespace(BluetoothVoiceRuntime=FakeBluetoothRuntime)
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(voice_module.importlib, "import_module", selective_import)

    async def scenario():
        auth = tmp_path / "cutover-test-authorization.json"
        auth.write_text(json.dumps({
            "schema": "eira2_cutover_authorization_v2",
            "accepted": True,
            "functional_preservation_verified": True,
        }), encoding="utf-8")

        config = replace(
            default_config(tmp_path),
            shadow_mode=False,
            terminal_enabled=True,
            voice_enabled=True,
            repair_enabled=False,
            self_evolution_enabled=False,
            neural_ui_enabled=False,
            cutover_authorization_path=auth,
        )

        generated = []
        verified = []
        accepted_text = "Eira end-to-end mouth bridge verified."

        async def generate(prompt):
            generated.append(prompt)
            return accepted_text

        async def verify(user_text, candidate):
            verified.append((user_text, candidate))
            return candidate

        runtime = Eira2Runtime(config, generate=generate, verify=verify)
        await runtime.start()
        try:
            result = await runtime.process("What services are in Eira's runtime?")
            assert result.verified is True
            assert result.response == accepted_text
            assert len(generated) == 1
            assert len(verified) == 1
            assert "<eira_capability_results>" in generated[0]
            assert "capability=runtime.status ok=true" in generated[0]
            assert "reasoning.provider" in generated[0]
            assert "capabilities.executor" in generated[0]

            assert len(instances) == 1
            speaker = instances[0]
            assert speaker.spoken == [accepted_text]
            assert speaker.played_on == ["bluez_output.11_22_33_44_55_66"]

            voice = runtime.voice_status()
            assert voice["preferred_bluetooth_device_name"] == "Flash Cube"
            assert voice["preferred_bluetooth_device_connected"] is True
            assert voice["preferred_bluetooth_sink"] == "bluez_output.11_22_33_44_55_66"
            assert voice["spoken_count"] == 1
        finally:
            await runtime.stop()

    asyncio.run(scenario())
