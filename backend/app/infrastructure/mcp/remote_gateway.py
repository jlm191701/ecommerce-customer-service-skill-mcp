from __future__ import annotations

from typing import Any

import httpx


class RemoteMCPGateway:
    """HTTP adapter for an external customer-service MCP-compatible server."""

    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/tools/call",
                    json={"name": name, "arguments": arguments},
                )
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            return {
                "tool": name,
                "status": "failed",
                "error_code": "remote_mcp_unavailable",
                "data": {"error": type(exc).__name__},
                "display_summary": "远程 MCP 服务暂时不可用，请稍后重试或转人工处理。",
                "suggested_next_actions": ["retry", "human_handoff"],
                "permission": {"checked": True, "allowed": False},
            }
        result = body.get("result") if isinstance(body, dict) else None
        if isinstance(result, dict):
            return result
        return {
            "tool": name,
            "status": "failed",
            "error_code": "invalid_remote_mcp_response",
            "display_summary": "远程 MCP 服务返回格式异常。",
            "suggested_next_actions": ["retry", "human_handoff"],
            "permission": {"checked": True, "allowed": False},
        }
