from typing import Any

from app.agent.actions import AgentAction, HandoffAction, Observation
from app.schemas.chat import (
    ChatAction,
    ChatRequest,
    ChatResponse,
    ConversationState,
    HandoffStatus,
    TraceEvent,
)


class TurnContext:
    def __init__(
        self,
        request: ChatRequest,
        state: ConversationState,
        trace_id: str,
        active_skill: str,
        available_capabilities: list[dict[str, str]] | None = None,
        available_tools: list[dict] | None = None,
    ) -> None:
        self.request = request
        self.state = state
        self.trace_id = trace_id
        self.active_skill = active_skill
        self.available_capabilities = available_capabilities or []
        self.available_tools = available_tools or []
        self.step_count = 0
        self.done = False
        self.final_answer = ""
        self.handoff_status = HandoffStatus()
        self.actions: list[ChatAction] = []
        self.observations: list[Observation] = []
        self.trace_events: list[TraceEvent] = []

    def emit_trace(
        self,
        event: str,
        details: dict[str, Any] | None = None,
        step: int | None = None,
    ) -> None:
        self.trace_events.append(
            TraceEvent(
                sequence=len(self.trace_events) + 1,
                event=event,
                step=self.step_count if step is None else step,
                details=details or {},
            )
        )

    def record(self, action: AgentAction, observation: Observation) -> None:
        next_step = self.step_count + 1
        action_name = self._action_name(action)
        if observation.action_id is None:
            observation.action_id = f"{self.trace_id}_step_{next_step:02d}"
        if observation.name is None:
            observation.name = action_name
        self.step_count = next_step
        self.observations.append(observation)
        self.actions.append(
            ChatAction(
                type=action.type,
                name=action_name,
                status=observation.status,
                summary=observation.summary,
            )
        )
        self.emit_trace(
            "action_observed",
            {
                "action_id": observation.action_id,
                "type": action.type,
                "name": action_name,
                "status": observation.status,
                "error_code": observation.error_code,
            },
            step=self.step_count,
        )

    def complete(self, answer: str) -> None:
        self.final_answer = answer
        self.done = True

    def request_handoff(self, action: HandoffAction) -> None:
        self.final_answer = action.summary
        self.handoff_status = HandoffStatus(required=True, reason=action.reason)
        self.done = True

    def to_response(self) -> ChatResponse:
        self.state.active_skill = self.active_skill
        return ChatResponse(
            answer=self.final_answer,
            conversation_state=self.state,
            actions=self.actions,
            handoff_status=self.handoff_status,
            trace_id=self.trace_id,
            trace_events=self.trace_events,
        )

    def latest_observation(self, action_type: str) -> Observation | None:
        for observation in reversed(self.observations):
            if observation.type == action_type:
                return observation
        return None

    def latest_llm_observation(self, purpose: str) -> Observation | None:
        for observation in reversed(self.observations):
            if observation.type == "llm" and observation.data.get("purpose") == purpose:
                return observation
        return None

    @staticmethod
    def _action_name(action: AgentAction) -> str:
        if action.type == "llm":
            return action.purpose
        if action.type == "capability":
            return action.capability
        if action.type == "mcp_tool":
            return action.tool_name
        if action.type == "transfer_skill":
            return action.target_skill
        return action.type
