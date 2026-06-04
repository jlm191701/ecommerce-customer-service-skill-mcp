from fastapi import APIRouter, Depends

from app.agent.dependencies import get_agent_runtime
from app.agent.runtime import AgentRuntime
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat/messages", response_model=ChatResponse)
async def create_chat_message(
    request: ChatRequest,
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> ChatResponse:
    return await runtime.run_turn(request)
