from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pymysql

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch


class VisionAnalyzer(Protocol):
    def analyze(self, *, question: str, images: list[str]) -> str:
        ...


@dataclass
class CustomerServiceMCPContext:
    knowledge_search: LocalKnowledgeSearch
    connection: pymysql.connections.Connection | None = None
    vision_analyzer: VisionAnalyzer | None = None


def require_connection(context: CustomerServiceMCPContext) -> pymysql.connections.Connection:
    if context.connection is None:
        raise RuntimeError("Database connection is required for this MCP tool.")
    return context.connection
