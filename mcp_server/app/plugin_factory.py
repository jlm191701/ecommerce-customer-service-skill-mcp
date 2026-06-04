from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.mcp.customer_service import CustomerServiceMCPPlugin
from app.infrastructure.mcp.customer_service.audit import MCPAuditLogger
from app.infrastructure.vision import QwenVisionClient
from mcp_server.app.config import settings


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password.get_secret_value() if settings.mysql_password else "",
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


@lru_cache
def get_plugin() -> CustomerServiceMCPPlugin:
    configured_knowledge_path = Path(settings.knowledge_path)
    knowledge_path = (
        configured_knowledge_path
        if configured_knowledge_path.is_absolute()
        else (PROJECT_ROOT / configured_knowledge_path)
    ).resolve()
    if not knowledge_path.exists() and not configured_knowledge_path.is_absolute():
        knowledge_path = (BACKEND_ROOT / configured_knowledge_path).resolve()
    if not knowledge_path.exists() and settings.knowledge_path.startswith("../backend/"):
        knowledge_path = (BACKEND_ROOT / settings.knowledge_path.removeprefix("../backend/")).resolve()
    audit_path = (PROJECT_ROOT / "mcp_server" / settings.audit_log_path).resolve()
    vision_analyzer = (
        QwenVisionClient(
            api_key=settings.qwen_vl_api_key.get_secret_value(),
            base_url=settings.qwen_vl_base_url,
            model=settings.qwen_vl_model,
            timeout_seconds=settings.vision_timeout_seconds,
        )
        if settings.qwen_vl_api_key
        else None
    )
    return CustomerServiceMCPPlugin(
        connection_factory=_connect,
        knowledge_search=LocalKnowledgeSearch(knowledge_path),
        vision_analyzer=vision_analyzer,
        audit_logger=MCPAuditLogger(audit_path),
    )
