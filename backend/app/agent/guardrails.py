from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.agent.actions import AgentAction, CapabilityAction, MCPToolAction, Observation
from app.agent.capabilities import CapabilityResolver
from app.agent.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from app.agent.context import TurnContext


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool = True
    rule: str | None = None
    error_code: str | None = None
    summary: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    suggested_next_actions: list[str] = field(default_factory=list)

    def to_observation(self, action_type: str) -> Observation:
        return Observation(
            type=action_type,
            status="failed",
            data={
                "status": "failed",
                "error_code": self.error_code,
                "guardrail_rule": self.rule,
                "details": self.details,
            },
            summary=self.summary,
            error_code=self.error_code,
            suggested_next_actions=self.suggested_next_actions,
        )


class GuardrailEngine:
    def __init__(
        self,
        *,
        capabilities: CapabilityResolver,
        tools: ToolRegistry,
    ) -> None:
        self._capabilities = capabilities
        self._tools = tools

    def before_action(
        self,
        action: AgentAction,
        context: TurnContext,
    ) -> GuardrailDecision:
        tool_name = self._tool_name_for_action(action)
        if not tool_name:
            return GuardrailDecision()

        schema = self._tools.get(tool_name)
        if not schema:
            return GuardrailDecision()

        if schema.requires_identity and not context.request.user_id.strip():
            return GuardrailDecision(
                allowed=False,
                rule="tool_requires_identity",
                error_code="guardrail_missing_identity",
                summary=f"Guardrail blocked {tool_name}: user identity is required.",
                details={"tool_name": tool_name},
                suggested_next_actions=["ask_user_to_login_or_verify"],
            )

        return GuardrailDecision()

    def after_observation(
        self,
        action: AgentAction,
        observation: Observation,
        context: TurnContext,
    ) -> None:
        if observation.status != "failed":
            return

        error_code = observation.error_code or str(observation.data.get("error_code") or "")
        if error_code not in {
            "permission_denied",
            "missing_identity",
            "guardrail_missing_identity",
        }:
            return

        context.state.task_state["guardrail_last_failure"] = {
            "action_type": action.type,
            "action_name": observation.name,
            "error_code": error_code,
        }
        context.emit_trace(
            "guardrail_flagged",
            {
                "rule": "sensitive_access_failed",
                "action_type": action.type,
                "action_name": observation.name,
                "error_code": error_code,
            },
            step=context.step_count,
        )

    def _tool_name_for_action(self, action: AgentAction) -> str | None:
        if isinstance(action, MCPToolAction):
            return action.tool_name
        if isinstance(action, CapabilityAction):
            tool = self._capabilities.resolve(action.capability)
            return tool.tool_name if tool else None
        return None
