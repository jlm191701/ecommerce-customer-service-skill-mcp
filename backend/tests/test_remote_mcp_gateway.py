import asyncio

import pytest

from app.infrastructure.mcp.remote_gateway import RemoteMCPGateway


class FakeResponse:
    def __init__(self, body: dict, status_error: Exception | None = None) -> None:
        self._body = body
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error:
            raise self._status_error

    def json(self) -> dict:
        return self._body


class FakeAsyncClient:
    calls: list[tuple[str, dict]] = []
    response: FakeResponse | None = None
    error: Exception | None = None

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        self.calls.append((url, json))
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def test_remote_mcp_gateway_calls_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.error = None
    FakeAsyncClient.response = FakeResponse(
        {
            "result": {
                "tool": "knowledge.search",
                "status": "success",
                "data": {"ok": True},
            }
        }
    )
    monkeypatch.setattr("app.infrastructure.mcp.remote_gateway.httpx.AsyncClient", FakeAsyncClient)

    gateway = RemoteMCPGateway(base_url="http://mcp.local/")
    result = asyncio.run(gateway.call_tool("knowledge.search", {"query": "价保"}))

    assert result["status"] == "success"
    assert FakeAsyncClient.calls == [
        (
            "http://mcp.local/tools/call",
            {"name": "knowledge.search", "arguments": {"query": "价保"}},
        )
    ]


def test_remote_mcp_gateway_returns_tool_failure_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = None
    FakeAsyncClient.error = RuntimeError("offline")
    monkeypatch.setattr("app.infrastructure.mcp.remote_gateway.httpx.AsyncClient", FakeAsyncClient)

    gateway = RemoteMCPGateway(base_url="http://mcp.local")
    result = asyncio.run(gateway.call_tool("order.lookup", {"order_id": "1"}))

    assert result["status"] == "failed"
    assert result["error_code"] == "remote_mcp_unavailable"
    assert result["tool"] == "order.lookup"
