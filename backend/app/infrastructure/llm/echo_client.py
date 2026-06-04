from typing import Any


class EchoLLMClient:
    async def complete(self, prompt: str, context: dict[str, Any]) -> str:
        return prompt
