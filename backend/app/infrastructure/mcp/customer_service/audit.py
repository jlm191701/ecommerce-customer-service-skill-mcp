from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any


class MCPAuditLogger:
    """Append-only JSONL audit logger for MCP tool calls."""

    SENSITIVE_KEYS = {
        "password",
        "password_hash",
        "token",
        "secret",
        "transaction_id",
        "phone",
        "email",
        "address",
    }

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        started_at: float,
    ) -> None:
        meta = arguments.get("_meta") if isinstance(arguments.get("_meta"), dict) else {}
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": meta.get("trace_id"),
            "conversation_id": meta.get("conversation_id") or arguments.get("conversation_id"),
            "user_id": arguments.get("user_id") or meta.get("user_id"),
            "tool": tool,
            "status": result.get("status"),
            "error_code": result.get("error_code"),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "arguments": self._summarize_arguments(arguments),
            "permission": self._summarize_permission(result.get("permission")),
            "suggested_next_actions": [
                str(action) for action in result.get("suggested_next_actions", [])
            ],
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _summarize_arguments(self, value: dict[str, Any]) -> dict[str, Any]:
        summarized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "_meta":
                continue
            lowered = key.lower()
            if any(sensitive in lowered for sensitive in self.SENSITIVE_KEYS):
                summarized[key] = "***"
            elif key in {"query", "description", "summary"}:
                summarized[key] = self._preview(item, 120)
            elif key in {
                "user_id",
                "order_id",
                "conversation_id",
                "tenant_id",
                "brand_id",
                "priority",
                "reason",
                "case_type",
                "related_order_id",
                "title",
                "limit",
            }:
                summarized[key] = item
            else:
                summarized[key] = self._preview(item, 80)
        return summarized

    @staticmethod
    def _summarize_permission(permission: Any) -> dict[str, Any]:
        if not isinstance(permission, dict):
            return {}
        return {
            key: permission.get(key)
            for key in ["checked", "allowed", "resource", "scope", "order_id"]
            if key in permission
        }

    @staticmethod
    def _preview(value: Any, limit: int) -> str:
        text = " ".join(str(value).split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
