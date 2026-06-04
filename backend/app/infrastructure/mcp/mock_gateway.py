from typing import Any
from pathlib import Path

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch


class MockMCPGateway:
    def __init__(
        self,
        knowledge_search: LocalKnowledgeSearch | None = None,
        vision_analyzer: Any | None = None,
    ) -> None:
        default_knowledge_path = Path(__file__).resolve().parents[3] / "knowledge"
        self._knowledge_search = knowledge_search or LocalKnowledgeSearch(default_knowledge_path)
        self._vision_analyzer = vision_analyzer

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "order.lookup":
            return self._lookup_order(arguments)
        if name == "shipment.lookup":
            return self._lookup_shipment(arguments)
        if name == "payment.lookup":
            return self._lookup_payment(arguments)
        if name == "after_sales.lookup":
            return self._lookup_after_sales(arguments)
        if name == "knowledge.search":
            return self._search_knowledge(arguments)
        if name == "vision.analyze":
            return self._analyze_vision(arguments)
        if name == "handoff.request":
            return self._request_handoff(arguments)
        if name == "ticket.create":
            return self._create_ticket(arguments)
        if name == "user.lookup":
            return self._lookup_user(arguments)

        return {
            "tool": name,
            "status": "mocked",
            "data": arguments,
            "display_summary": "MCP gateway is reserved and currently mocked.",
            "suggested_next_actions": ["replace_with_real_mcp_server"],
            "permission": {"checked": True, "allowed": True},
        }

    def _lookup_order(self, arguments: dict[str, Any]) -> dict[str, Any]:
        order_id = str(arguments.get("order_id") or "").strip()
        user_id = str(arguments.get("user_id") or "").strip()

        if not order_id:
            return {
                "tool": "order.lookup",
                "status": "failed",
                "error_code": "missing_order_id",
                "display_summary": "缺少订单号，无法查询订单。",
                "suggested_next_actions": ["ask_user_for_order_id"],
                "permission": {"checked": True, "allowed": False},
            }

        data = {
            "order_id": order_id,
            "user_id": user_id,
            "order_status": "shipping",
            "payment_status": "paid",
            "logistics_status": "out_for_delivery",
            "carrier": "Mock Express",
            "tracking_number": f"MOCK{order_id[-8:]}",
            "estimated_delivery_time": "今天 18:00 前",
            "last_update": "包裹已到达所在城市，正在派送中。",
        }

        return {
            "tool": "order.lookup",
            "status": "success",
            "data": data,
            "display_summary": (
                f"订单 {order_id} 已支付，当前正在派送中，预计今天 18:00 前送达。"
            ),
            "suggested_next_actions": [
                "reply_to_user",
                "offer_handoff_if_user_is_unsatisfied",
            ],
            "permission": {"checked": True, "allowed": True},
        }

    def _lookup_shipment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = self._lookup_order(arguments)
        if base.get("status") == "failed":
            base["tool"] = "shipment.lookup"
            return base
        data = {
            key: base["data"].get(key)
            for key in [
                "order_id",
                "order_status",
                "logistics_status",
                "carrier",
                "tracking_number",
                "estimated_delivery_time",
                "last_update",
            ]
        }
        return {
            "tool": "shipment.lookup",
            "status": "success",
            "data": data,
            "display_summary": f"订单 {data['order_id']} 当前正在派送中，预计今天 18:00 前送达。",
            "suggested_next_actions": ["reply_to_user", "offer_handoff_if_user_is_unsatisfied"],
            "permission": {
                "checked": True,
                "allowed": True,
                "resource": "shipment",
                "scope": "own_order",
                "order_id": data["order_id"],
            },
        }

    def _lookup_payment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = self._lookup_order(arguments)
        if base.get("status") == "failed":
            base["tool"] = "payment.lookup"
            return base
        order_id = base["data"]["order_id"]
        return {
            "tool": "payment.lookup",
            "status": "success",
            "data": {
                "order_id": order_id,
                "order_status": base["data"]["order_status"],
                "payment_status": "paid",
                "payment_method": "mock_pay",
                "paid_amount": "4999.00",
                "transaction_id_masked": "********0001",
            },
            "display_summary": f"订单 {order_id} 支付状态为 paid，支付方式为 mock_pay。",
            "suggested_next_actions": ["reply_to_user", "human_handoff_if_payment_dispute"],
            "permission": {
                "checked": True,
                "allowed": True,
                "resource": "payment",
                "scope": "own_order",
                "order_id": order_id,
            },
        }

    def _lookup_after_sales(self, arguments: dict[str, Any]) -> dict[str, Any]:
        base = self._lookup_order(arguments)
        if base.get("status") == "failed":
            base["tool"] = "after_sales.lookup"
            return base
        order_id = base["data"]["order_id"]
        return {
            "tool": "after_sales.lookup",
            "status": "success",
            "data": {
                "order_id": order_id,
                "order_status": base["data"]["order_status"],
                "after_sales": [],
            },
            "display_summary": f"订单 {order_id} 暂无售后记录。",
            "suggested_next_actions": ["reply_to_user", "create_ticket_if_needed"],
            "permission": {
                "checked": True,
                "allowed": True,
                "resource": "after_sales",
                "scope": "own_order",
                "order_id": order_id,
            },
        }

    def _search_knowledge(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        limit = arguments.get("limit")
        return self._knowledge_search.search(query, limit if isinstance(limit, int) else None)

    def _analyze_vision(self, arguments: dict[str, Any]) -> dict[str, Any]:
        question = str(arguments.get("question") or "").strip()
        raw_images = arguments.get("images")
        images = [str(image) for image in raw_images] if isinstance(raw_images, list) else []
        images = [image for image in images if image.startswith(("data:image/", "http://", "https://"))]
        if not images:
            return {
                "tool": "vision.analyze",
                "status": "failed",
                "error_code": "missing_image",
                "display_summary": "未收到可识别的图片，请重新上传图片。",
                "suggested_next_actions": ["ask_user_to_reupload_image"],
                "permission": {"checked": True, "allowed": False},
            }
        if self._vision_analyzer is None:
            return {
                "tool": "vision.analyze",
                "status": "success",
                "data": {
                    "question": question,
                    "image_count": len(images[:4]),
                    "analysis": "我已收到图片。当前 mock 模式未配置真实视觉模型，只能确认图片已上传。",
                },
                "display_summary": "我已收到图片。当前 mock 模式未配置真实视觉模型，只能确认图片已上传。",
                "suggested_next_actions": ["reply_to_user"],
                "permission": {"checked": True, "allowed": True},
            }
        try:
            answer = self._vision_analyzer.analyze(question=question, images=images[:4])
        except Exception as exc:
            return {
                "tool": "vision.analyze",
                "status": "failed",
                "error_code": "vision_model_error",
                "data": {"error": type(exc).__name__},
                "display_summary": "图片理解暂时失败，请稍后重试或转人工处理。",
                "suggested_next_actions": ["retry", "human_handoff"],
                "permission": {"checked": True, "allowed": False},
            }
        return {
            "tool": "vision.analyze",
            "status": "success",
            "data": {"question": question, "image_count": len(images[:4]), "analysis": answer},
            "display_summary": answer,
            "suggested_next_actions": ["reply_to_user", "ask_follow_up_if_needed"],
            "permission": {"checked": True, "allowed": True},
        }

    def _request_handoff(self, arguments: dict[str, Any]) -> dict[str, Any]:
        reason = str(arguments.get("reason") or "user_requested_human")
        conversation_id = str(arguments.get("conversation_id") or "")
        handoff_id = f"HO-{abs(hash(conversation_id + reason)) % 1000000:06d}"
        return {
            "tool": "handoff.request",
            "status": "success",
            "data": {
                "handoff_id": handoff_id,
                "reason": reason,
                "status": "queued",
            },
            "display_summary": f"已为您提交人工客服转接请求，排队编号 {handoff_id}。",
            "suggested_next_actions": ["reply_to_user"],
            "permission": {"checked": True, "allowed": True},
        }

    def _create_ticket(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title") or "客服跟进工单")
        user_id = str(arguments.get("user_id") or "")
        ticket_id = f"TK-{abs(hash(title + user_id)) % 1000000:06d}"
        return {
            "tool": "ticket.create",
            "status": "success",
            "data": {
                "ticket_id": ticket_id,
                "title": title,
                "status": "created",
                "priority": arguments.get("priority") or "normal",
            },
            "display_summary": f"已创建工单 {ticket_id}，客服会根据记录继续跟进。",
            "suggested_next_actions": ["reply_to_user", "offer_handoff_if_urgent"],
            "permission": {"checked": True, "allowed": True},
        }

    def _lookup_user(self, arguments: dict[str, Any]) -> dict[str, Any]:
        user_id = str(arguments.get("user_id") or "").strip()
        if not user_id:
            return {
                "tool": "user.lookup",
                "status": "failed",
                "error_code": "missing_user_id",
                "display_summary": "缺少用户 ID，无法查询用户上下文。",
                "suggested_next_actions": ["ask_user_to_login_or_verify"],
                "permission": {"checked": True, "allowed": False},
            }

        return {
            "tool": "user.lookup",
            "status": "success",
            "data": {
                "identity": {
                    "user_id": user_id,
                    "display_name": user_id,
                    "account_status": "active",
                    "authenticated": True,
                    "scope": "self",
                },
                "preferences": {"preferred_language": "zh-CN"},
                "membership": {
                    "member_level": "mock_member",
                    "points": 0,
                    "growth_value": 0,
                },
                "contact_hints": {
                    "phone_masked": None,
                    "email_masked": None,
                    "full_contact_hidden": True,
                },
                "recent_order_hint": "64575145823542368",
                "recent_orders": [
                    {
                        "order_id": "64575145823542368",
                        "order_status": "shipping",
                        "created_at": None,
                    }
                ],
            },
            "display_summary": f"已获取用户 {user_id} 的基础服务上下文。",
            "suggested_next_actions": ["use_context_for_service"],
            "permission": {
                "checked": True,
                "allowed": True,
                "resource": "user_context",
                "scope": "self",
                "user_id": user_id,
            },
        }
