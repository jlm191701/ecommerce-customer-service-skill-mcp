from functools import lru_cache
from pathlib import Path

from app.agent.capabilities import default_capability_resolver
from app.agent.registry import SkillRegistry
from app.agent.runtime import AgentRuntime
from app.core.config import settings
from app.infrastructure.llm.deepseek_client import DeepSeekLLMClient
from app.infrastructure.llm.echo_client import EchoLLMClient
from app.infrastructure.llm.query_planner import DeepSeekQueryPlannerClient
from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.memory.event_entity_store import EventEntityMemoryStore
from app.infrastructure.mcp.mock_gateway import MockMCPGateway
from app.infrastructure.mcp.mysql_gateway import MySQLMCPGateway
from app.infrastructure.mcp.remote_gateway import RemoteMCPGateway
from app.infrastructure.skills.file_loader import FileSkillLoader
from app.infrastructure.sessions.memory_store import InMemorySessionStore
from app.infrastructure.vision import QwenVisionClient


@lru_cache
def get_agent_runtime() -> AgentRuntime:
    sessions = InMemorySessionStore()
    skills_path = (Path(__file__).resolve().parents[2] / settings.skills_path).resolve()
    registry = SkillRegistry(skills=FileSkillLoader(skills_path).load())
    llm = (
        DeepSeekLLMClient(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        if settings.deepseek_api_key
        else EchoLLMClient()
    )
    query_planner = (
        DeepSeekQueryPlannerClient(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=min(settings.llm_timeout_seconds, 10.0),
        )
        if settings.deepseek_api_key
        else None
    )
    knowledge_path = (Path(__file__).resolve().parents[2] / settings.knowledge_path).resolve()
    knowledge_search = LocalKnowledgeSearch(knowledge_path, query_planner=query_planner)
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
    if settings.mcp_backend.lower() == "remote":
        mcp = RemoteMCPGateway(
            base_url=settings.mcp_server_url,
            timeout_seconds=settings.mcp_timeout_seconds,
        )
    elif settings.mcp_backend.lower() == "mysql":
        mcp = MySQLMCPGateway(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=(
                settings.mysql_password.get_secret_value()
                if settings.mysql_password
                else ""
            ),
            database=settings.mysql_database,
            knowledge_search=knowledge_search,
            vision_analyzer=vision_analyzer,
        )
    else:
        mcp = MockMCPGateway(
            knowledge_search=knowledge_search,
            vision_analyzer=vision_analyzer,
        )
    memory_path = (Path(__file__).resolve().parents[2] / settings.memory_path).resolve()
    long_term_memory = EventEntityMemoryStore(memory_path)
    return AgentRuntime(
        sessions=sessions,
        registry=registry,
        llm=llm,
        mcp=mcp,
        long_term_memory=long_term_memory,
        capabilities=default_capability_resolver(),
        recent_message_limit=settings.recent_message_limit,
    )
