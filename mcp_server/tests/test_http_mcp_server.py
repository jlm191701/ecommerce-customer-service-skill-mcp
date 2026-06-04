from pathlib import Path
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from mcp_server.app.main import create_app


def test_mcp_server_lists_tools() -> None:
    client = TestClient(create_app())

    response = client.get("/tools")

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert "knowledge.search" in names
    assert "vision.analyze" in names
    assert "order.lookup" in names


def test_mcp_server_calls_public_knowledge_tool() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/tools/call",
        json={
            "name": "knowledge.search",
            "arguments": {"query": "Aurora Phone X1 快充", "limit": 1},
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "success"
    assert result["tool"] == "knowledge.search"
