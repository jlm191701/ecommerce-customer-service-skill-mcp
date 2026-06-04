from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.capabilities import default_capability_resolver
from app.agent.dependencies import get_agent_runtime
from app.agent.registry import SkillRegistry
from app.agent.runtime import AgentRuntime
from app.infrastructure.llm.echo_client import EchoLLMClient
from app.infrastructure.memory.markdown_store import MarkdownLongTermMemoryStore
from app.infrastructure.mcp.mock_gateway import MockMCPGateway
from app.infrastructure.skills.file_loader import FileSkillLoader
from app.infrastructure.sessions.memory_store import InMemorySessionStore
from app.main import create_app


class IntentThenEchoLLMClient:
    async def complete(self, prompt: str, context: dict) -> str:
        if context.get("user_message"):
            return (
                '{"intent":"after_sales_policy","confidence":0.86,'
                '"slots":{},"capability":null,'
                '"references":["after_sales_playbook.md","ticket_playbook.md"]}'
            )
        return prompt


class MissingOrderPlannerLLMClient:
    async def complete(self, prompt: str, context: dict) -> str:
        if context.get("user_message"):
            return (
                '{"intent":"order_overview","confidence":0.82,'
                '"slots":{},"capability":"order_lookup",'
                '"references":["order_playbook.md","identity_policy.md"],'
                '"fallback":{"action":"ask_order_id","reason":"missing_order_id"}}'
            )
        return prompt


class FakeVisionAnalyzer:
    def analyze(self, *, question: str, images: list[str]) -> str:
        return f"看到 {len(images)} 张图片，用户问题是：{question}"


class FakeCatalogVisionAnalyzer:
    def analyze(self, *, question: str, images: list[str]) -> str:
        return "图片中可见文字为：苹果 iPhone 17e。图片像是一张手机商品宣传图。"


def test_chat_message_returns_runtime_response() -> None:
    app = create_app()
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_default")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=[]),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_test",
            "user_id": "user_test",
            "message": "Where is my order?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_skill"] == "default_agent"
    assert body["conversation_state"]["active_intent"] == "general_chat"
    assert body["trace_id"].startswith("trace_")
    assert [action["type"] for action in body["actions"]] == ["llm", "final_answer"]
    assert len(body["conversation_state"]["recent_messages"]) == 2
    trace_events = [event["event"] for event in body["trace_events"]]
    assert trace_events == [
        "turn_started",
        "skill_selected",
        "action_planned",
        "action_observed",
        "action_planned",
        "action_observed",
        "state_saved",
        "turn_completed",
    ]


def test_chat_message_uses_loaded_customer_service_skill() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_skill")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_customer_service",
            "user_id": "user_test",
            "message": "你是谁？你是 DeepSeek 吗？",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_skill"] == "customer_service_core"
    assert [action["name"] for action in body["actions"]] == [
        "intent_recognition",
        "response_generation",
        "final_answer",
    ]
    memory_file = Path(__file__).resolve().parent / ".tmp_memory_skill" / "users" / "user_test.md"
    memory_content = memory_file.read_text(encoding="utf-8")
    assert "用户 ID：user_test" in memory_content
    assert "偏好使用中文沟通。" in memory_content
    assert "你是谁？你是 DeepSeek 吗？" not in memory_content


def test_order_lookup_uses_mock_mcp_tool() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_order")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_order_lookup",
            "user_id": "user_test",
            "message": "帮我查询一下订单号 64575145823542368 的物流",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_intent"] == "shipment_status"
    plan = body["conversation_state"]["task_state"]["structured_plan"]
    assert plan["version"] == "skill_plan.v1"
    assert plan["intent"] == "shipment_status"
    assert plan["capability"] == "shipment_lookup"
    assert plan["slots"]["order_id"] == "64575145823542368"
    assert plan["missing_slots"] == []
    assert plan["next_step"] == "use_capability:shipment_lookup"
    assert body["actions"][0]["type"] == "capability"
    assert body["actions"][0]["name"] == "shipment_lookup"
    assert [action["type"] for action in body["actions"]] == [
        "capability",
        "llm",
        "final_answer",
    ]


@pytest.mark.parametrize(
    ("message", "expected_intent", "expected_capability"),
    [
        ("退货规则是什么？", "after_sales_policy", "knowledge_search"),
        ("订单 64575145823542368 扣款成功了吗？", "payment_status", "payment_lookup"),
        ("订单 64575145823542368 的退款进度怎么样？", "after_sales_status", "after_sales_lookup"),
        ("我要人工客服", "handoff", "human_handoff"),
        ("我要投诉，物流太慢了", "complaint", "ticket_create"),
        ("帮我看看我的会员资料", "identity_verification", "user_lookup"),
        ("帮我创建一个工单记录这个问题", "ticket", "ticket_create"),
    ],
)
def test_customer_service_capability_mocks(
    message: str,
    expected_intent: str,
    expected_capability: str,
) -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_capabilities")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": f"conv_{expected_capability}",
            "user_id": "user_test",
            "message": message,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_intent"] == expected_intent
    assert body["actions"][0]["type"] == "capability"
    assert body["actions"][0]["name"] == expected_capability
    assert [action["type"] for action in body["actions"]] == [
        "capability",
        "llm",
        "final_answer",
    ]


def test_intent_recognition_fallback_can_select_references() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_intent")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=IntentThenEchoLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_intent",
            "user_id": "user_test",
            "message": "这个东西坏了怎么办",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_intent"] == "after_sales_policy"
    assert body["conversation_state"]["task_state"]["selected_references"] == [
        "after_sales_playbook.md",
        "ticket_playbook.md",
    ]
    assert [action["name"] for action in body["actions"]] == [
        "intent_recognition",
        "response_generation",
        "final_answer",
    ]


def test_structured_planner_falls_back_when_order_id_missing() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_missing_order")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=MissingOrderPlannerLLMClient(),
        mcp=MockMCPGateway(),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_missing_order",
            "user_id": "user_test",
            "message": "帮我查一下订单状态",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_intent"] == "order_overview"
    assert [action["type"] for action in body["actions"]] == ["llm", "ask_user"]
    assert "订单号" in body["answer"]
    plan = body["conversation_state"]["task_state"]["structured_plan"]
    assert plan["capability"] == "order_lookup"
    assert plan["missing_slots"] == ["order_id"]
    assert plan["fallback"] == {
        "action": "ask_order_id",
        "reason": "missing_order_id",
    }
    assert plan["next_step"] == "ask_order_id"


def test_image_message_routes_to_vision_capability() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_vision")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(vision_analyzer=FakeVisionAnalyzer()),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_vision",
            "user_id": "user_test",
            "message": "帮我看看这张图是什么问题",
            "context": {
                "images": [
                    {
                        "name": "issue.png",
                        "data_url": "data:image/png;base64,ZmFrZQ==",
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_state"]["active_intent"] == "image_question"
    assert body["actions"][0]["type"] == "capability"
    assert body["actions"][0]["name"] == "vision_analyze"
    plan = body["conversation_state"]["task_state"]["structured_plan"]
    assert plan["capability"] == "vision_analyze"
    assert plan["slots"]["image_count"] == 1
    assert plan["next_step"] == "use_capability:vision_analyze"


def test_image_product_question_checks_knowledge_after_vision() -> None:
    app = create_app()
    repo_root = Path(__file__).resolve().parents[2]
    memory = MarkdownLongTermMemoryStore(Path(__file__).resolve().parent / ".tmp_memory_vision_catalog")
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=FileSkillLoader(repo_root / "skills").load()),
        llm=EchoLLMClient(),
        mcp=MockMCPGateway(vision_analyzer=FakeCatalogVisionAnalyzer()),
        long_term_memory=memory,
        capabilities=default_capability_resolver(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/chat/messages",
        json={
            "conversation_id": "conv_vision_catalog",
            "user_id": "user_test",
            "message": "卖这个吗？",
            "context": {
                "images": [
                    {
                        "name": "iphone17e.png",
                        "data_url": "data:image/png;base64,ZmFrZQ==",
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [action["name"] for action in body["actions"]] == [
        "vision_analyze",
        "knowledge_search",
        "response_generation",
        "final_answer",
    ]
    assert body["conversation_state"]["task_state"]["image_knowledge_checked"] is True
    assert "iPhone 17e" in body["conversation_state"]["task_state"]["image_knowledge_query"]
