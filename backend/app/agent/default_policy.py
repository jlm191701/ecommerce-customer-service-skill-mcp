from app.agent.actions import AgentAction, FinalAnswerAction, LLMAction
from app.agent.context import TurnContext


class DefaultAgentPolicy:
    name = "default_agent"

    async def next_action(self, context: TurnContext) -> AgentAction:
        context.state.active_skill = None
        context.state.active_intent = "general_chat"
        context.state.summary = f"Latest user message: {context.request.message}"

        llm_observation = context.latest_observation("llm")
        if llm_observation and llm_observation.content:
            return FinalAnswerAction(answer=llm_observation.content)

        return LLMAction(
            prompt=context.request.message,
            context={
                "system_prompt": (
                    "You are a general-purpose assistant inside a standard agent "
                    "framework. No domain skills or MCP tools are loaded for this "
                    "turn. Have a concise, natural conversation and do not claim "
                    "access to external business systems."
                ),
                "conversation_state": context.state.model_dump(),
                "recent_messages": [
                    message.model_dump() for message in context.state.recent_messages
                ],
                "long_term_memory": context.state.long_term_memory,
            },
        )
