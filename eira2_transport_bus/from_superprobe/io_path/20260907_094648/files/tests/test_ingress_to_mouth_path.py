import asyncio

from eira2.interfaces.ingress import InputKind
from eira2.runtime import Eira2Runtime, default_config


def test_runtime_process_enters_through_ingress_and_preserves_one_delivery(tmp_path):
    async def scenario():
        generated = []

        async def generate(text):
            generated.append(text)
            return "candidate:" + text

        async def verify(user_text, candidate):
            return candidate

        runtime = Eira2Runtime(default_config(tmp_path), generate=generate, verify=verify)
        await runtime.start()
        result = await runtime.process("hello end to end", kind=InputKind.TERMINAL)
        assert result.verified is True
        assert len(generated) == 1
        assert len(runtime.history.recent()) == 1
        await runtime.stop()

    asyncio.run(scenario())
