from __future__ import annotations

from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.mcp.customer_service import CustomerServiceMCPPlugin


class MySQLMCPGateway:
    """Thin adapter that exposes the customer-service MCP plugin through MySQL."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        knowledge_search: LocalKnowledgeSearch,
        vision_analyzer: Any | None = None,
    ) -> None:
        self._connection_kwargs = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "charset": "utf8mb4",
            "cursorclass": DictCursor,
            "autocommit": False,
        }
        self._plugin = CustomerServiceMCPPlugin(
            connection_factory=self._connect,
            knowledge_search=knowledge_search,
            vision_analyzer=vision_analyzer,
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._plugin.call_tool(name, arguments)

    def describe_tools(self) -> list[dict[str, Any]]:
        return self._plugin.describe()

    def _connect(self) -> pymysql.connections.Connection:
        return pymysql.connect(**self._connection_kwargs)
