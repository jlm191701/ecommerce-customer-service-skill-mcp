from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def order_summary(order: dict[str, Any]) -> str:
    product = order["items"][0]["product_name"] if order.get("items") else "订单商品"
    logistics = order.get("logistics_status") or "暂无物流状态"
    eta = order.get("estimated_delivery_time")
    if eta:
        return f"订单 {order['order_id']} 包含 {product}，当前物流状态为 {logistics}，预计送达时间 {eta}。"
    return f"订单 {order['order_id']} 包含 {product}，当前订单状态为 {order.get('order_status')}。"


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def failed_result(
    tool: str,
    error_code: str,
    summary: str,
    next_actions: list[str],
    *,
    allowed: bool,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "status": "failed",
        "error_code": error_code,
        "data": data or {},
        "display_summary": summary,
        "suggested_next_actions": next_actions,
        "permission": {"checked": True, "allowed": allowed},
    }
