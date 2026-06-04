from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any, Callable

import pymysql

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.mcp.customer_service.audit import MCPAuditLogger
from app.infrastructure.mcp.customer_service.context import CustomerServiceMCPContext
from app.infrastructure.mcp.customer_service.tools import (
    AfterSalesLookupTool,
    CustomerServiceTool,
    HandoffRequestTool,
    KnowledgeSearchTool,
    OrderLookupTool,
    PaymentLookupTool,
    ShipmentLookupTool,
    TicketCreateTool,
    UserLookupTool,
    VisionAnalyzeTool,
)
from app.infrastructure.mcp.customer_service.utils import failed_result


ConnectionFactory = Callable[[], pymysql.connections.Connection]


class CustomerServiceMCPPlugin:
    """Pluggable MCP tool package for customer-service capabilities."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        knowledge_search: LocalKnowledgeSearch,
        vision_analyzer: Any | None = None,
        tools: list[CustomerServiceTool] | None = None,
        audit_logger: MCPAuditLogger | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._knowledge_search = knowledge_search
        self._vision_analyzer = vision_analyzer
        self._audit_logger = audit_logger or MCPAuditLogger(
            Path(__file__).resolve().parents[4] / "logs" / "mcp_audit.jsonl"
        )
        self._tools = {
            tool.name: tool
            for tool in (
                tools
                or [
                    KnowledgeSearchTool(),
                    VisionAnalyzeTool(),
                    UserLookupTool(),
                    OrderLookupTool(),
                    ShipmentLookupTool(),
                    PaymentLookupTool(),
                    AfterSalesLookupTool(),
                    TicketCreateTool(),
                    HandoffRequestTool(),
                ]
            )
        }

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "requires_database": tool.requires_database,
            }
            for tool in self._tools.values()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started_at = time.perf_counter()
        tool = self._tools.get(name)
        if not tool:
            result = failed_result(
                name,
                "unknown_tool",
                f"未接入工具 {name}。",
                ["human_handoff"],
                allowed=False,
                data=arguments,
            )
            self._audit(name, arguments, result, started_at)
            return result

        if not tool.requires_database:
            context = CustomerServiceMCPContext(
                knowledge_search=self._knowledge_search,
                vision_analyzer=self._vision_analyzer,
            )
            result = tool.run(arguments, context)
            self._audit(name, arguments, result, started_at)
            return result

        try:
            result = await asyncio.to_thread(self._run_with_connection, tool, arguments)
        except Exception as exc:
            result = failed_result(
                name,
                "upstream_error",
                "数据库查询暂时失败，请稍后重试或转人工处理。",
                ["retry", "human_handoff"],
                allowed=False,
                data={"error": type(exc).__name__},
            )
        self._audit(name, arguments, result, started_at)
        return result

    def _run_with_connection(
        self,
        tool: CustomerServiceTool,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            context = CustomerServiceMCPContext(
                knowledge_search=self._knowledge_search,
                connection=connection,
                vision_analyzer=self._vision_analyzer,
            )
            result = tool.run(arguments, context)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _audit(
        self,
        name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        started_at: float,
    ) -> None:
        try:
            self._audit_logger.record(
                tool=name,
                arguments=arguments,
                result=result,
                started_at=started_at,
            )
        except Exception:
            # Audit failures must never break the customer-service path.
            return None
