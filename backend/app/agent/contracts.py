from typing import Any, Protocol

from app.agent.actions import AgentAction
from app.agent.context import TurnContext
from app.schemas.chat import ChatRequest, ConversationState


class SessionStore(Protocol):
    async def get_state(self, conversation_id: str) -> ConversationState:
        ...

    async def save_state(self, conversation_id: str, state: ConversationState) -> None:
        ...


class LLMClient(Protocol):
    async def complete(self, prompt: str, context: dict[str, Any]) -> str:
        ...


class MCPGateway(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...


class LongTermMemoryStore(Protocol):
    async def load(self, user_id: str) -> str:
        ...

    async def update_from_turn(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        ...


class Skill(Protocol):
    name: str
    description: str
    priority: int

    def can_handle(self, request: ChatRequest, state: ConversationState) -> float:
        ...

    async def next_action(self, context: TurnContext) -> AgentAction:
        ...
