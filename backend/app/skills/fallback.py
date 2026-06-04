from app.agent.actions import AgentAction, FinalAnswerAction, LLMAction
from app.agent.context import TurnContext
from app.schemas.chat import ChatRequest, ConversationState


class FallbackSkill:
    name = "fallback"
    description = "Default customer-service skill used until domain skills are added."
    priority = 0

    def can_handle(self, request: ChatRequest, state: ConversationState) -> float:
        return 0.1

    async def next_action(self, context: TurnContext) -> AgentAction:
        request = context.request
        state = context.state
        state.active_skill = self.name
        state.active_intent = "fallback"
        state.summary = f"Latest user message: {request.message}"

        llm_observation = context.latest_observation("llm")
        if llm_observation and llm_observation.content:
            return FinalAnswerAction(answer=llm_observation.content)

        return LLMAction(
            prompt=request.message,
            context={
                "system_prompt": (
                    "You are the fallback skill in a customer service agent runtime. "
                    "Reply briefly, acknowledge the user's need, and explain that domain "
                    "skills and MCP tools will be connected next."
                ),
                "conversation_state": state.model_dump(),
            },
        )
