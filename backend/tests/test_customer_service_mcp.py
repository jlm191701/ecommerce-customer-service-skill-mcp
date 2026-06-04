from pathlib import Path
from typing import Any

import pymysql

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.mcp.customer_service import CustomerServiceMCPPlugin
from app.infrastructure.mcp.customer_service.audit import MCPAuditLogger
from app.infrastructure.mcp.customer_service.context import CustomerServiceMCPContext
from app.infrastructure.mcp.customer_service.tools import (
    PaymentLookupTool,
    ShipmentLookupTool,
    UserLookupTool,
)


def test_customer_service_mcp_plugin_describes_registered_tools(tmp_path: Path) -> None:
    plugin = CustomerServiceMCPPlugin(
        connection_factory=lambda: pymysql.connect(),
        knowledge_search=LocalKnowledgeSearch(tmp_path),
    )

    tools = plugin.describe()
    tool_names = {tool["name"] for tool in tools}

    assert tool_names == {
        "after_sales.lookup",
        "knowledge.search",
        "vision.analyze",
        "user.lookup",
        "order.lookup",
        "payment.lookup",
        "shipment.lookup",
        "ticket.create",
        "handoff.request",
    }
    assert next(tool for tool in tools if tool["name"] == "knowledge.search")[
        "requires_database"
    ] is False
    assert next(tool for tool in tools if tool["name"] == "vision.analyze")[
        "requires_database"
    ] is False
    assert next(tool for tool in tools if tool["name"] == "order.lookup")[
        "requires_database"
    ] is True


class FakeCursor:
    def __init__(self, order_user_id: str = "user_test") -> None:
        self.order_user_id = order_user_id
        self._result: Any = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if "FROM orders" in sql:
            self._result = {
                "order_id": params[0],
                "user_id": self.order_user_id,
                "order_status": "shipping",
                "total_amount": "4999.00",
                "currency": "CNY",
                "created_at": None,
                "paid_at": None,
                "completed_at": None,
            }
        elif "FROM payments" in sql:
            self._result = {
                "payment_status": "paid",
                "payment_method": "alipay",
                "paid_amount": "4999.00",
                "transaction_id": "PAY202606010001",
                "paid_at": None,
            }
        elif "FROM shipments" in sql:
            self._result = {
                "logistics_status": "out_for_delivery",
                "carrier": "顺丰速运",
                "tracking_number": "SF202606010888",
                "estimated_delivery_time": "今天 18:00 前",
                "last_update": "正在派送中。",
                "shipped_at": None,
                "delivered_at": None,
            }
        else:
            self._result = None

    def fetchone(self) -> Any:
        return self._result

    def fetchall(self) -> list[Any]:
        return self._result if isinstance(self._result, list) else []


class FakeUserCursor(FakeCursor):
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if "FROM users u" in sql:
            self._result = {
                "user_id": params[0],
                "display_name": "测试用户",
                "phone_masked": "138****8001",
                "email_masked": "te***@example.com",
                "preferred_language": "zh-CN",
                "account_status": "active",
                "member_level": "gold",
                "points": 100,
                "growth_value": 200,
            }
        elif "FROM orders" in sql:
            self._result = [
                {
                    "order_id": "64575145823542368",
                    "order_status": "shipping",
                    "created_at": None,
                }
            ]
        else:
            self._result = None


class FakeConnection:
    def __init__(self, order_user_id: str = "user_test") -> None:
        self.order_user_id = order_user_id

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.order_user_id)


class FakeUserConnection(FakeConnection):
    def cursor(self) -> FakeUserCursor:
        return FakeUserCursor(self.order_user_id)


def test_user_lookup_returns_safe_service_context(tmp_path: Path) -> None:
    tool = UserLookupTool()
    result = tool.run(
        {"user_id": "user_test"},
        CustomerServiceMCPContext(
            knowledge_search=LocalKnowledgeSearch(tmp_path),
            connection=FakeUserConnection(),
        ),
    )

    assert result["status"] == "success"
    assert result["data"]["identity"] == {
        "user_id": "user_test",
        "display_name": "测试用户",
        "account_status": "active",
        "authenticated": True,
        "scope": "self",
    }
    assert result["data"]["contact_hints"]["full_contact_hidden"] is True
    assert result["data"]["recent_order_hint"] == "64575145823542368"
    assert "password" not in str(result["data"]).lower()


def test_payment_lookup_masks_sensitive_transaction_id(tmp_path: Path) -> None:
    tool = PaymentLookupTool()
    result = tool.run(
        {"order_id": "64575145823542368", "user_id": "user_test"},
        CustomerServiceMCPContext(
            knowledge_search=LocalKnowledgeSearch(tmp_path),
            connection=FakeConnection(),
        ),
    )

    assert result["status"] == "success"
    assert result["data"]["transaction_id_masked"].endswith("0001")
    assert "PAY202606010001" not in str(result["data"])
    assert result["permission"]["resource"] == "payment"


def test_shipment_lookup_rejects_cross_user_order(tmp_path: Path) -> None:
    tool = ShipmentLookupTool()
    result = tool.run(
        {"order_id": "64575145823542368", "user_id": "user_test"},
        CustomerServiceMCPContext(
            knowledge_search=LocalKnowledgeSearch(tmp_path),
            connection=FakeConnection(order_user_id="other_user"),
        ),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "permission_denied"
    assert result["permission"]["allowed"] is False


async def _call_plugin(plugin: CustomerServiceMCPPlugin, arguments: dict[str, Any]) -> dict[str, Any]:
    return await plugin.call_tool("knowledge.search", arguments)


class FakeVisionAnalyzer:
    def analyze(self, *, question: str, images: list[str]) -> str:
        return f"图片数量 {len(images)}，问题：{question}"


async def _call_vision_plugin(
    plugin: CustomerServiceMCPPlugin,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return await plugin.call_tool("vision.analyze", arguments)


def test_customer_service_mcp_plugin_runs_knowledge_tool_without_database(tmp_path: Path) -> None:
    card = tmp_path / "product" / "phone.md"
    card.parent.mkdir()
    card.write_text(
        """---
title: Aurora Phone X1 参数
category: product
keywords:
  - Aurora Phone X1
  - 快充
---

Aurora Phone X1 支持最高 80W 有线快充。
""",
        encoding="utf-8",
    )

    def fail_if_called() -> pymysql.connections.Connection:
        raise AssertionError("knowledge.search should not open a database connection")

    plugin = CustomerServiceMCPPlugin(
        connection_factory=fail_if_called,
        knowledge_search=LocalKnowledgeSearch(tmp_path),
    )

    import asyncio

    result = asyncio.run(_call_plugin(plugin, {"query": "Aurora Phone X1 快充"}))

    assert result["status"] == "success"
    assert result["data"]["results"][0]["title"] == "Aurora Phone X1 参数"


def test_customer_service_mcp_plugin_runs_vision_tool_without_database(tmp_path: Path) -> None:
    def fail_if_called() -> pymysql.connections.Connection:
        raise AssertionError("vision.analyze should not open a database connection")

    plugin = CustomerServiceMCPPlugin(
        connection_factory=fail_if_called,
        knowledge_search=LocalKnowledgeSearch(tmp_path),
        vision_analyzer=FakeVisionAnalyzer(),
    )

    import asyncio

    result = asyncio.run(
        _call_vision_plugin(
            plugin,
            {
                "question": "这是什么商品？",
                "images": ["data:image/png;base64,ZmFrZQ=="],
            },
        )
    )

    assert result["status"] == "success"
    assert result["data"]["image_count"] == 1
    assert "这是什么商品" in result["data"]["analysis"]


def test_customer_service_mcp_plugin_writes_audit_log(tmp_path: Path) -> None:
    card = tmp_path / "product" / "phone.md"
    card.parent.mkdir()
    card.write_text(
        """---
title: Aurora Phone X1 参数
category: product
keywords:
  - Aurora Phone X1
---

Aurora Phone X1 支持最高 80W 有线快充。
""",
        encoding="utf-8",
    )
    audit_path = tmp_path / "audit" / "mcp.jsonl"
    plugin = CustomerServiceMCPPlugin(
        connection_factory=lambda: pymysql.connect(),
        knowledge_search=LocalKnowledgeSearch(tmp_path),
        audit_logger=MCPAuditLogger(audit_path),
    )

    import asyncio

    result = asyncio.run(
        plugin.call_tool(
            "knowledge.search",
            {
                "query": "Aurora Phone X1 快充",
                "_meta": {"trace_id": "trace_test", "conversation_id": "conv_test"},
            },
        )
    )

    entry = audit_path.read_text(encoding="utf-8")
    assert result["status"] == "success"
    assert '"trace_id": "trace_test"' in entry
    assert '"tool": "knowledge.search"' in entry
    assert '"status": "success"' in entry
