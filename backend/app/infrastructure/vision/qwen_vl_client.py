from __future__ import annotations

from typing import Any

import httpx


class QwenVisionClient:
    """Small OpenAI-compatible client for Qwen VL image understanding."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    def analyze(self, *, question: str, images: list[str]) -> str:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是数码电商客服的视觉理解助手，只负责描述图片中可见内容。"
                    "如果图片是商品、包装、故障截图、支付截图、物流截图或售后凭证，"
                    "请提取对客服处理有用的信息。不要编造图片中看不到的内容。"
                    "不要判断商品是否真实发布、是否在售、是否正品、官方是否发布、价格或参数是否准确；"
                    "这些时效性和业务事实必须交给商品目录或知识库查询。"
                    f"\n\n用户问题：{question}"
                ),
            }
        ]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": image},
            }
            for image in images
        )
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "stream": False,
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

        return str(body["choices"][0]["message"]["content"])
