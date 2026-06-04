from uuid import uuid4

from app.agent.capabilities import CapabilityResolver
from app.agent.contracts import LLMClient, LongTermMemoryStore, MCPGateway, SessionStore
from app.agent.context import TurnContext
from app.agent.default_policy import DefaultAgentPolicy
from app.agent.executor import ActionExecutor
from app.agent.guardrails import GuardrailEngine
from app.agent.registry import SkillRegistry
from app.agent.tool_registry import ToolRegistry, default_tool_registry
from app.schemas.chat import ChatRequest, ChatResponse, MemoryMessage


class AgentRuntime:
    """Runs the observe-act loop for one conversation turn."""

    def __init__(
        self,
        sessions: SessionStore,
        registry: SkillRegistry,
        llm: LLMClient,
        mcp: MCPGateway,
        long_term_memory: LongTermMemoryStore,
        capabilities: CapabilityResolver,
        tools: ToolRegistry | None = None,
        guardrails: GuardrailEngine | None = None,
        max_steps: int = 8,
        recent_message_limit: int = 10,
    ) -> None:
        self._sessions = sessions
        self._registry = registry
        self._tools = tools or default_tool_registry()
        self._guardrails = guardrails or GuardrailEngine(
            capabilities=capabilities,
            tools=self._tools,
        )
        self._executor = ActionExecutor(
            llm=llm,
            mcp=mcp,
            capabilities=capabilities,
            tools=self._tools,
        )
        self._long_term_memory = long_term_memory
        self._capabilities = capabilities
        self._max_steps = max_steps
        self._recent_message_limit = recent_message_limit

    async def run_turn(self, request: ChatRequest) -> ChatResponse:
        trace_id = f"trace_{uuid4().hex}"
        state = await self._sessions.get_state(request.conversation_id)
        state.long_term_memory = await self._load_long_term_memory(request)
        skill = self._registry.select(request, state)
        policy = skill or DefaultAgentPolicy()
        context = TurnContext(
            request=request,
            state=state,
            trace_id=trace_id,
            active_skill=policy.name,
            available_capabilities=self._capabilities.describe(),
            available_tools=self._tools.describe(),
        )
        context.emit_trace(
            "turn_started",
            {
                "conversation_id": request.conversation_id,
                "channel": request.channel,
            },
            step=0,
        )
        context.emit_trace(
            "skill_selected",
            {
                "skill": policy.name,
                "matched": skill is not None,
            },
            step=0,
        )

        while not context.done and context.step_count < self._max_steps:
            action = await policy.next_action(context)
            context.emit_trace(
                "action_planned",
                {
                    "type": action.type,
                    "name": context._action_name(action),
                },
                step=context.step_count + 1,
            )
            guardrail_decision = self._guardrails.before_action(action, context)
            if guardrail_decision.allowed:
                observation = await self._executor.execute(action, context)
            else:
                context.emit_trace(
                    "guardrail_blocked",
                    {
                        "rule": guardrail_decision.rule,
                        "error_code": guardrail_decision.error_code,
                        "action_type": action.type,
                        "action_name": context._action_name(action),
                    },
                    step=context.step_count + 1,
                )
                observation = guardrail_decision.to_observation(action.type)
            context.record(action, observation)
            self._guardrails.after_observation(action, observation, context)

        if not context.done:
            context.emit_trace(
                "step_limit_reached",
                {"max_steps": self._max_steps},
                step=context.step_count,
            )
            context.complete(
                "The agent reached its step limit before completing this turn. "
                "Please try again or request human support."
            )

        context.state.recent_messages = self._updated_recent_messages(
            context.state.recent_messages,
            request.message,
            context.final_answer,
        )
        await self._long_term_memory.update_from_turn(
            request.user_id,
            request.message,
            context.final_answer,
        )
        await self._sessions.save_state(request.conversation_id, context.state)
        context.emit_trace(
            "state_saved",
            {
                "recent_messages": len(context.state.recent_messages),
            },
            step=context.step_count,
        )
        context.emit_trace("turn_completed", step=context.step_count)
        return context.to_response()

    async def _load_long_term_memory(self, request: ChatRequest) -> str:
        retrieve = getattr(self._long_term_memory, "retrieve", None)
        if retrieve is not None:
            return await retrieve(request.user_id, request.message)
        return await self._long_term_memory.load(request.user_id)

    def _updated_recent_messages(
        self,
        current: list[MemoryMessage],
        user_message: str,
        assistant_message: str,
    ) -> list[MemoryMessage]:
        updated = [
            *current,
            MemoryMessage(role="user", content=user_message),
            MemoryMessage(role="assistant", content=assistant_message),
        ]
        return updated[-self._recent_message_limit :]
