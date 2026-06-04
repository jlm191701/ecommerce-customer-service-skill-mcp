from app.schemas.chat import ConversationState


class InMemorySessionStore:
    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}

    async def get_state(self, conversation_id: str) -> ConversationState:
        return self._states.get(conversation_id, ConversationState())

    async def save_state(self, conversation_id: str, state: ConversationState) -> None:
        self._states[conversation_id] = state
