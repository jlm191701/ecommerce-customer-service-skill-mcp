from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMAction(BaseModel):
    type: Literal["llm"] = "llm"
    purpose: str = "response_generation"
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class MCPToolAction(BaseModel):
    type: Literal["mcp_tool"] = "mcp_tool"
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CapabilityAction(BaseModel):
    type: Literal["capability"] = "capability"
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FinalAnswerAction(BaseModel):
    type: Literal["final_answer"] = "final_answer"
    answer: str


class AskUserAction(BaseModel):
    type: Literal["ask_user"] = "ask_user"
    question: str


class HandoffAction(BaseModel):
    type: Literal["handoff"] = "handoff"
    reason: str
    summary: str


class TransferSkillAction(BaseModel):
    type: Literal["transfer_skill"] = "transfer_skill"
    target_skill: str
    reason: str


AgentAction = (
    LLMAction
    | MCPToolAction
    | CapabilityAction
    | FinalAnswerAction
    | AskUserAction
    | HandoffAction
    | TransferSkillAction
)


class Observation(BaseModel):
    action_id: str | None = None
    type: str
    name: str | None = None
    status: Literal["success", "failed", "terminal"] = "success"
    content: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    error_code: str | None = None
    suggested_next_actions: list[str] = Field(default_factory=list)
