from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: str
    tenant_id: str | None = None
    brand_id: str | None = None
    channel: Literal["web"] = "web"
    context: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False


class MemoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ConversationState(BaseModel):
    active_skill: str | None = None
    active_intent: str | None = None
    summary: str = ""
    task_state: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[MemoryMessage] = Field(default_factory=list)
    long_term_memory: str = ""


class ChatAction(BaseModel):
    type: str
    name: str
    status: str
    summary: str | None = None


class TraceEvent(BaseModel):
    sequence: int
    event: str
    step: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HandoffStatus(BaseModel):
    required: bool = False
    reason: str | None = None


class ChatResponse(BaseModel):
    answer: str
    conversation_state: ConversationState
    actions: list[ChatAction] = Field(default_factory=list)
    handoff_status: HandoffStatus = Field(default_factory=HandoffStatus)
    trace_id: str
    trace_events: list[TraceEvent] = Field(default_factory=list)
