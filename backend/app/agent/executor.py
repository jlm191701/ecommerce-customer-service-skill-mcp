from typing import Any

from app.agent.actions import (
    AgentAction,
    AskUserAction,
    CapabilityAction,
    FinalAnswerAction,
    HandoffAction,
    LLMAction,
    MCPToolAction,
    Observation,
    TransferSkillAction,
)
from app.agent.capabilities import CapabilityResolver
from app.agent.contracts import LLMClient, MCPGateway
from app.agent.context import TurnContext
from app.agent.tool_registry import ToolRegistry, ToolValidationResult, default_tool_registry


class ActionExecutor:
    def __init__(
        self,
        llm: LLMClient,
        mcp: MCPGateway,
        capabilities: CapabilityResolver,
        tools: ToolRegistry | None = None,
    ) -> None:
        self._llm = llm
        self._mcp = mcp
        self._capabilities = capabilities
        self._tools = tools or default_tool_registry()

    async def execute(self, action: AgentAction, context: TurnContext) -> Observation:
        if isinstance(action, LLMAction):
            return await self._execute_llm(action)
        if isinstance(action, CapabilityAction):
            return await self._execute_capability(action, context)
        if isinstance(action, MCPToolAction):
            return await self._execute_mcp_tool(action, context)
        if isinstance(action, FinalAnswerAction):
            context.complete(action.answer)
            return Observation(
                type=action.type,
                status="terminal",
                content=action.answer,
                summary="Final answer produced.",
            )
        if isinstance(action, AskUserAction):
            context.complete(action.question)
            return Observation(
                type=action.type,
                status="terminal",
                content=action.question,
                summary="Asked user for more information.",
            )
        if isinstance(action, HandoffAction):
            context.request_handoff(action)
            return Observation(
                type=action.type,
                status="terminal",
                content=action.summary,
                summary=action.reason,
            )
        if isinstance(action, TransferSkillAction):
            return Observation(
                type=action.type,
                status="failed",
                data={"target_skill": action.target_skill},
                summary="Skill transfer is reserved but not implemented yet.",
                error_code="transfer_skill_not_implemented",
                suggested_next_actions=["fallback_to_current_skill"],
            )

        return Observation(
            type="unknown",
            status="failed",
            summary="Unsupported action.",
            error_code="unsupported_action",
        )

    async def _execute_llm(self, action: LLMAction) -> Observation:
        answer = await self._llm.complete(action.prompt, action.context)
        return Observation(
            type=action.type,
            status="success",
            content=answer,
            data={"purpose": action.purpose},
            summary="LLM completion produced.",
        )

    async def _execute_mcp_tool(
        self,
        action: MCPToolAction,
        context: TurnContext,
    ) -> Observation:
        validation = self._tools.validate(
            action.tool_name,
            action.arguments,
            context.request,
        )
        if not validation.valid:
            return self._tool_validation_observation(
                action.type,
                action.tool_name,
                validation,
            )

        result = await self._mcp.call_tool(
            action.tool_name,
            self._arguments_with_meta(action.arguments, context),
        )
        return self._tool_result_observation(action.type, result)

    async def _execute_capability(
        self,
        action: CapabilityAction,
        context: TurnContext,
    ) -> Observation:
        tool = self._capabilities.resolve(action.capability)
        if not tool:
            return Observation(
                type=action.type,
                status="failed",
                data={
                    "status": "missing_capability",
                    "capability": action.capability,
                },
                summary=f"Missing capability: {action.capability}",
                error_code="missing_capability",
                suggested_next_actions=["fallback_to_default_response"],
            )

        validation = self._tools.validate(
            tool.tool_name,
            action.arguments,
            context.request,
        )
        if not validation.valid:
            return self._tool_validation_observation(
                action.type,
                tool.tool_name,
                validation,
            )

        result = await self._mcp.call_tool(
            tool.tool_name,
            self._arguments_with_meta(action.arguments, context),
        )
        result["capability"] = action.capability
        result["resolved_tool"] = tool.tool_name
        return self._tool_result_observation(action.type, result)

    @staticmethod
    def _arguments_with_meta(
        arguments: dict[str, Any],
        context: TurnContext,
    ) -> dict[str, Any]:
        updated = dict(arguments)
        meta = updated.get("_meta") if isinstance(updated.get("_meta"), dict) else {}
        updated["_meta"] = {
            **meta,
            "trace_id": context.trace_id,
            "conversation_id": context.request.conversation_id,
            "user_id": context.request.user_id,
            "channel": context.request.channel,
        }
        return updated

    @staticmethod
    def _tool_result_observation(action_type: str, result: dict[str, Any]) -> Observation:
        return Observation(
            type=action_type,
            status="success" if result.get("status") != "failed" else "failed",
            data=result,
            summary=result.get("display_summary"),
            error_code=result.get("error_code"),
            suggested_next_actions=[
                str(action) for action in result.get("suggested_next_actions", [])
            ],
        )

    @staticmethod
    def _tool_validation_observation(
        action_type: str,
        tool_name: str,
        validation: ToolValidationResult,
    ) -> Observation:
        return Observation(
            type=action_type,
            status="failed",
            data={
                "tool": tool_name,
                "status": "failed",
                "error_code": validation.error_code,
                "details": validation.details,
            },
            summary=validation.message,
            error_code=validation.error_code,
        )
