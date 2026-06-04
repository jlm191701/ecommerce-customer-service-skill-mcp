from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas.chat import ChatRequest


ParameterType = Literal["string", "integer", "number", "boolean", "object", "array"]


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: ParameterType
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    requires_identity: bool = False
    permission_level: Literal["public", "user", "privileged"] = "public"
    failure_next_actions: list[str] = field(default_factory=list)
    allow_extra_arguments: bool = True


@dataclass(frozen=True)
class ToolValidationResult:
    valid: bool
    error_code: str | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self, schemas: list[ToolSchema]) -> None:
        self._schemas = {schema.name: schema for schema in schemas}

    def get(self, name: str) -> ToolSchema | None:
        return self._schemas.get(name)

    def list(self) -> list[ToolSchema]:
        return list(self._schemas.values())

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": schema.name,
                "description": schema.description,
                "requires_identity": schema.requires_identity,
                "permission_level": schema.permission_level,
                "parameters": [
                    {
                        "name": parameter.name,
                        "type": parameter.type,
                        "required": parameter.required,
                        "description": parameter.description,
                    }
                    for parameter in schema.parameters
                ],
            }
            for schema in self._schemas.values()
        ]

    def validate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        request: ChatRequest,
    ) -> ToolValidationResult:
        schema = self.get(tool_name)
        if not schema:
            return ToolValidationResult(
                valid=False,
                error_code="unknown_tool",
                message=f"Tool is not registered: {tool_name}",
                details={"tool_name": tool_name},
            )

        if schema.requires_identity and not request.user_id.strip():
            return ToolValidationResult(
                valid=False,
                error_code="missing_identity",
                message=f"Tool requires an authenticated user context: {tool_name}",
                details={"tool_name": tool_name},
            )

        known_parameters = {parameter.name: parameter for parameter in schema.parameters}
        missing = [
            parameter.name
            for parameter in schema.parameters
            if parameter.required and self._is_missing(arguments.get(parameter.name))
        ]
        if missing:
            return ToolValidationResult(
                valid=False,
                error_code="missing_required_arguments",
                message=f"Tool call is missing required arguments: {', '.join(missing)}",
                details={"tool_name": tool_name, "missing": missing},
            )

        if not schema.allow_extra_arguments:
            extra = sorted(set(arguments) - set(known_parameters))
            if extra:
                return ToolValidationResult(
                    valid=False,
                    error_code="unexpected_arguments",
                    message=f"Tool call has unexpected arguments: {', '.join(extra)}",
                    details={"tool_name": tool_name, "extra": extra},
                )

        type_errors: list[dict[str, str]] = []
        for name, value in arguments.items():
            parameter = known_parameters.get(name)
            if not parameter or value is None:
                continue
            if not self._matches_type(value, parameter.type):
                type_errors.append(
                    {
                        "name": name,
                        "expected": parameter.type,
                        "actual": type(value).__name__,
                    }
                )

        if type_errors:
            return ToolValidationResult(
                valid=False,
                error_code="invalid_argument_type",
                message="Tool call has invalid argument types.",
                details={"tool_name": tool_name, "type_errors": type_errors},
            )

        return ToolValidationResult(valid=True)

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        return False

    @staticmethod
    def _matches_type(value: Any, parameter_type: ParameterType) -> bool:
        if parameter_type == "string":
            return isinstance(value, str)
        if parameter_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if parameter_type == "number":
            return isinstance(value, int | float) and not isinstance(value, bool)
        if parameter_type == "boolean":
            return isinstance(value, bool)
        if parameter_type == "object":
            return isinstance(value, dict)
        if parameter_type == "array":
            return isinstance(value, list)
        return False


def default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        schemas=[
            ToolSchema(
                name="knowledge.search",
                description="Search customer-service knowledge cards and policies.",
                parameters=[
                    ToolParameter("query", "string", required=True),
                    ToolParameter("limit", "integer"),
                    ToolParameter("user_id", "string"),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                ],
                permission_level="public",
                failure_next_actions=["retry_with_clearer_query", "human_handoff"],
            ),
            ToolSchema(
                name="vision.analyze",
                description="Analyze user-provided images for customer-service context.",
                parameters=[
                    ToolParameter("question", "string", required=True),
                    ToolParameter("images", "array", required=True),
                    ToolParameter("user_id", "string"),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                ],
                permission_level="public",
                failure_next_actions=["ask_user_to_reupload_image", "human_handoff"],
            ),
            ToolSchema(
                name="user.lookup",
                description="Look up the current user's service profile.",
                parameters=[
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["ask_user_to_login_or_verify"],
            ),
            ToolSchema(
                name="order.lookup",
                description="Look up order overview and purchased items.",
                parameters=[
                    ToolParameter("order_id", "string", required=True),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                    ToolParameter("conversation_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["ask_user_for_order_id", "ask_user_for_verification"],
            ),
            ToolSchema(
                name="shipment.lookup",
                description="Look up shipment and delivery status for an owned order.",
                parameters=[
                    ToolParameter("order_id", "string", required=True),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                    ToolParameter("conversation_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["ask_user_for_order_id", "ask_user_for_verification"],
            ),
            ToolSchema(
                name="payment.lookup",
                description="Look up payment status for an owned order with sensitive values masked.",
                parameters=[
                    ToolParameter("order_id", "string", required=True),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                    ToolParameter("conversation_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["ask_user_for_order_id", "ask_user_for_verification"],
            ),
            ToolSchema(
                name="after_sales.lookup",
                description="Look up after-sales cases for an owned order.",
                parameters=[
                    ToolParameter("order_id", "string", required=True),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("tenant_id", "string"),
                    ToolParameter("brand_id", "string"),
                    ToolParameter("conversation_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["ask_user_for_order_id", "ask_user_for_verification"],
            ),
            ToolSchema(
                name="ticket.create",
                description="Create a support ticket for follow-up.",
                parameters=[
                    ToolParameter("title", "string", required=True),
                    ToolParameter("description", "string", required=True),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("conversation_id", "string"),
                    ToolParameter("priority", "string"),
                    ToolParameter("case_type", "string"),
                    ToolParameter("related_order_id", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["retry", "human_handoff"],
            ),
            ToolSchema(
                name="handoff.request",
                description="Request a human customer-service handoff.",
                parameters=[
                    ToolParameter("reason", "string", required=True),
                    ToolParameter("summary", "string"),
                    ToolParameter("user_id", "string", required=True),
                    ToolParameter("conversation_id", "string"),
                    ToolParameter("priority", "string"),
                ],
                requires_identity=True,
                permission_level="user",
                failure_next_actions=["reply_to_user"],
            ),
        ]
    )
