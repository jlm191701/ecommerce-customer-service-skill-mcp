from fastapi import Depends, FastAPI

from mcp_server.app.config import settings
from mcp_server.app.plugin_factory import get_plugin
from mcp_server.app.schemas import ToolCallRequest, ToolCallResponse


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "customer_service_mcp"}

    @app.get("/tools")
    async def list_tools(
        plugin=Depends(get_plugin),
    ) -> dict[str, list[dict]]:
        return {"tools": plugin.describe()}

    @app.post("/tools/call", response_model=ToolCallResponse)
    async def call_tool(
        request: ToolCallRequest,
        plugin=Depends(get_plugin),
    ) -> ToolCallResponse:
        return ToolCallResponse(
            result=await plugin.call_tool(request.name, request.arguments)
        )

    return app


app = create_app()
