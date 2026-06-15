from __future__ import annotations

from typing import Any
import json

import httpx


class DeepSeekQueryPlannerClient:
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

    def complete(self, prompt: str, context: dict[str, Any]) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a query planner for a customer-service knowledge base. "
                        "Return compact JSON only. Do not answer the user."
                    ),
                },
                {"role": "user", "content": self._build_user_content(prompt, context)},
            ],
            "stream": False,
            "temperature": 0,
        }

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(
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
        return (
            f"{prompt}\n\n"
            "Context:\n"
            f"```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
        )
