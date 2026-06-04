from typing import Any

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    result: dict[str, Any]
