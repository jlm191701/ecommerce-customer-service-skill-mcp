import asyncio
from typing import Any

from app.agent.actions import AgentAction, CapabilityAction, FinalAnswerAction, Observation
from app.agent.capabilities import default_capability_resolver
from app.agent.context import TurnContext
from app.agent.executor import ActionExecutor
from app.agent.registry import SkillRegistry
from app.agent.runtime import AgentRuntime
from app.agent.tool_registry import default_tool_registry
from app.schemas.chat import ChatRequest, ConversationState
from app.infrastructure.sessions.memory_store import InMemorySessionStore


class FakeLLMClient:
    async def complete(self, prompt: str, context: dict[str, Any]) -> str:
        return prompt


class RecordingMCPGateway:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if self._result is not None:
            return self._result
        return {
            "tool": name,
            "status": "success",
            "data": arguments,
            "display_summary": "Tool call completed.",
        }


class MemoryStore:
    async def load(self, user_id: str) -> str:
        return ""

    async def update_from_turn(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        return None


class IdentityRequiredSkill:
    name = "identity_required_skill"
    description = "Test skill that calls an identity-required capability."
    priority = 100

    def can_handle(self, request: ChatRequest, state: ConversationState) -> float:
        return 1.0

    async def next_action(self, context: TurnContext) -> AgentAction:
        if context.latest_observation("capability"):
            return FinalAnswerAction(answer="blocked")
        return CapabilityAction(
            capability="user_lookup",
            arguments={"user_id": ""},
        )


def make_context() -> TurnContext:
    return TurnContext(
        request=ChatRequest(
            conversation_id="conv_test",
            user_id="user_test",
            message="test",
        ),
        state=ConversationState(),
        trace_id="trace_test",
        active_skill="test_skill",
    )


def test_default_tool_registry_describes_customer_service_tools() -> None:
    tools = default_tool_registry().describe()
    tool_names = {tool["name"] for tool in tools}

    assert tool_names == {
        "after_sales.lookup",
        "knowledge.search",
        "vision.analyze",
        "user.lookup",
        "order.lookup",
        "payment.lookup",
        "shipment.lookup",
        "ticket.create",
        "handoff.request",
    }
    order_lookup = next(tool for tool in tools if tool["name"] == "order.lookup")
    required = {
        parameter["name"]
        for parameter in order_lookup["parameters"]
        if parameter["required"]
    }
    assert required == {"order_id", "user_id"}
    assert order_lookup["requires_identity"] is True
    shipment_lookup = next(tool for tool in tools if tool["name"] == "shipment.lookup")
    assert shipment_lookup["requires_identity"] is True
    vision_analyze = next(tool for tool in tools if tool["name"] == "vision.analyze")
    vision_required = {
        parameter["name"]
        for parameter in vision_analyze["parameters"]
        if parameter["required"]
    }
    assert vision_required == {"question", "images"}
    assert vision_analyze["requires_identity"] is False


def test_executor_rejects_capability_call_missing_required_tool_argument() -> None:
    mcp = RecordingMCPGateway()
    executor = ActionExecutor(
        llm=FakeLLMClient(),
        mcp=mcp,
        capabilities=default_capability_resolver(),
    )

    observation = asyncio.run(
        executor.execute(
            CapabilityAction(
                capability="order_lookup",
                arguments={"user_id": "user_test"},
            ),
            make_context(),
        )
    )

    assert observation.status == "failed"
    assert observation.data["error_code"] == "missing_required_arguments"
    assert observation.data["details"]["missing"] == ["order_id"]
    assert mcp.calls == []


def test_executor_allows_valid_capability_call_after_tool_validation() -> None:
    mcp = RecordingMCPGateway()
    executor = ActionExecutor(
        llm=FakeLLMClient(),
        mcp=mcp,
        capabilities=default_capability_resolver(),
    )

    observation = asyncio.run(
        executor.execute(
            CapabilityAction(
                capability="order_lookup",
                arguments={
                    "order_id": "64575145823542368",
                    "user_id": "user_test",
                },
            ),
            make_context(),
        )
    )

    assert observation.status == "success"
    assert mcp.calls == [
        (
            "order.lookup",
            {
                "order_id": "64575145823542368",
                "user_id": "user_test",
                "_meta": {
                    "trace_id": "trace_test",
                    "conversation_id": "conv_test",
                    "user_id": "user_test",
                    "channel": "web",
                },
            },
        )
    ]


def test_context_record_adds_standard_action_result_metadata() -> None:
    context = make_context()

    context.record(
        FinalAnswerAction(answer="done"),
        Observation(type="final_answer", status="terminal", content="done"),
    )

    assert context.observations[0].action_id == "trace_test_step_01"
    assert context.observations[0].name == "final_answer"
    assert context.actions[0].name == "final_answer"


def test_executor_normalizes_failed_tool_result_metadata() -> None:
    mcp = RecordingMCPGateway(
        result={
            "tool": "order.lookup",
            "status": "failed",
            "error_code": "permission_denied",
            "display_summary": "Permission denied.",
            "suggested_next_actions": ["ask_user_for_verification", "human_handoff"],
        }
    )
    executor = ActionExecutor(
        llm=FakeLLMClient(),
        mcp=mcp,
        capabilities=default_capability_resolver(),
    )

    observation = asyncio.run(
        executor.execute(
            CapabilityAction(
                capability="order_lookup",
                arguments={
                    "order_id": "64575145823542368",
                    "user_id": "user_test",
                },
            ),
            make_context(),
        )
    )

    assert observation.status == "failed"
    assert observation.error_code == "permission_denied"
    assert observation.suggested_next_actions == [
        "ask_user_for_verification",
        "human_handoff",
    ]


def test_runtime_guardrail_blocks_identity_required_tool_before_mcp() -> None:
    mcp = RecordingMCPGateway()
    runtime = AgentRuntime(
        sessions=InMemorySessionStore(),
        registry=SkillRegistry(skills=[IdentityRequiredSkill()]),
        llm=FakeLLMClient(),
        mcp=mcp,
        long_term_memory=MemoryStore(),
        capabilities=default_capability_resolver(),
    )

    response = asyncio.run(
        runtime.run_turn(
            ChatRequest(
                conversation_id="conv_guardrail",
                user_id="",
                message="look up my profile",
            )
        )
    )

    assert mcp.calls == []
    assert response.actions[0].status == "failed"
    assert response.conversation_state.task_state["guardrail_last_failure"] == {
        "action_type": "capability",
        "action_name": "user_lookup",
        "error_code": "guardrail_missing_identity",
    }
    assert "guardrail_blocked" in [event.event for event in response.trace_events]
    assert "guardrail_flagged" in [event.event for event in response.trace_events]
