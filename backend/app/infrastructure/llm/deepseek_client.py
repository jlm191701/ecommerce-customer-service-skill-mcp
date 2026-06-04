from typing import Any
import json

import httpx


class DeepSeekLLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def complete(self, prompt: str, context: dict[str, Any]) -> str:
        system_prompt = context.get(
            "system_prompt",
            "You are a helpful customer service agent.",
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._build_user_content(prompt, context)},
            ],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        return body["choices"][0]["message"]["content"]

    @staticmethod
    def _build_user_content(prompt: str, context: dict[str, Any]) -> str:
        visible_context = {
            key: value
            for key, value in context.items()
            if key != "system_prompt" and value not in (None, "", [], {})
        }
        if not visible_context:
            return prompt
        return (
            "以下是本轮可用上下文，请结合上下文回答，不要逐字复述内部字段。\n\n"
            f"```json\n{json.dumps(visible_context, ensure_ascii=False, indent=2)}\n```\n\n"
            f"用户消息：{prompt}"
        )
