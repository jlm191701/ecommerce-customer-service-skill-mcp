from __future__ import annotations

from typing import Any, Protocol

from app.infrastructure.mcp.customer_service.context import (
    CustomerServiceMCPContext,
    require_connection,
)
from app.infrastructure.mcp.customer_service.utils import failed_result, jsonable, order_summary


class CustomerServiceTool(Protocol):
    name: str
    requires_database: bool

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        ...


class KnowledgeSearchTool:
    name = "knowledge.search"
    requires_database = False

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        limit = arguments.get("limit")
        return context.knowledge_search.search(query, limit if isinstance(limit, int) else None)


class VisionAnalyzeTool:
    name = "vision.analyze"
    requires_database = False

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        question = str(arguments.get("question") or "").strip()
        raw_images = arguments.get("images")
        images = [str(image) for image in raw_images] if isinstance(raw_images, list) else []
        images = [image for image in images if image.startswith(("data:image/", "http://", "https://"))]
        if not question:
            return failed_result(
                self.name,
                "missing_question",
                "缺少图片问题，无法进行图片理解。",
                ["ask_user_for_question"],
                allowed=False,
            )
        if not images:
            return failed_result(
                self.name,
                "missing_image",
                "未收到可识别的图片，请重新上传图片。",
                ["ask_user_to_reupload_image"],
                allowed=False,
            )
        if context.vision_analyzer is None:
            return failed_result(
                self.name,
                "vision_model_not_configured",
                "视觉模型暂未配置，当前无法查看图片。",
                ["configure_vision_model", "human_handoff"],
                allowed=False,
            )
        try:
            answer = context.vision_analyzer.analyze(question=question, images=images[:4])
        except Exception as exc:
            return failed_result(
                self.name,
                "vision_model_error",
                "图片理解暂时失败，请稍后重试或转人工处理。",
                ["retry", "human_handoff"],
                allowed=False,
                data={"error": type(exc).__name__},
            )
        return {
            "tool": self.name,
            "status": "success",
            "data": {
                "question": question,
                "image_count": len(images[:4]),
                "analysis": answer,
            },
            "display_summary": answer,
            "suggested_next_actions": ["reply_to_user", "ask_follow_up_if_needed"],
            "permission": {"checked": True, "allowed": True, "resource": "user_uploaded_image"},
        }


def _missing_order_result(tool: str) -> dict[str, Any]:
    return failed_result(
        tool,
        "missing_order_id",
        "缺少订单号，无法查询订单。",
        ["ask_user_for_order_id"],
        allowed=False,
    )


def _missing_user_result(tool: str) -> dict[str, Any]:
    return failed_result(
        tool,
        "missing_user_id",
        "缺少用户身份，无法查询订单相关信息。",
        ["ask_user_to_login_or_verify"],
        allowed=False,
    )


def _fetch_owned_order(
    cursor: Any,
    *,
    tool: str,
    order_id: str,
    user_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not order_id:
        return None, _missing_order_result(tool)
    if not user_id:
        return None, _missing_user_result(tool)

    cursor.execute(
        """
        SELECT order_id, user_id, order_status, total_amount, currency,
               created_at, paid_at, completed_at
        FROM orders
        WHERE order_id = %s
        """,
        (order_id,),
    )
    order = cursor.fetchone()
    if not order:
        return None, failed_result(
            tool,
            "not_found",
            "未找到该订单，请确认订单号是否正确。",
            ["ask_user_for_order_id"],
            allowed=False,
            data={"order_id": order_id},
        )
    if order["user_id"] != user_id:
        return None, failed_result(
            tool,
            "permission_denied",
            "为了保护账户安全，当前身份不能查询这笔订单。",
            ["ask_user_for_verification", "human_handoff"],
            allowed=False,
            data={"order_id": order_id, "requested_user_id": user_id},
        )
    return order, None


def _permission_ok(resource: str, order_id: str) -> dict[str, Any]:
    return {
        "checked": True,
        "allowed": True,
        "resource": resource,
        "scope": "own_order",
        "order_id": order_id,
    }


def _mask_transaction_id(transaction_id: Any) -> str | None:
    if not transaction_id:
        return None
    text = str(transaction_id)
    if len(text) <= 4:
        return "*" * len(text)
    return f"{'*' * max(len(text) - 4, 4)}{text[-4:]}"


class UserLookupTool:
    name = "user.lookup"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        user_id = str(arguments.get("user_id") or "").strip()
        if not user_id:
            return failed_result(
                self.name,
                "missing_user_id",
                "缺少用户 ID，无法查询用户上下文。",
                ["ask_user_to_login_or_verify"],
                allowed=False,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.user_id, u.display_name, u.phone_masked, u.email_masked,
                       u.preferred_language, u.account_status,
                       m.member_level, m.points, m.growth_value
                FROM users u
                LEFT JOIN memberships m ON m.user_id = u.user_id
                WHERE u.user_id = %s
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if not user:
                return failed_result(
                    self.name,
                    "not_found",
                    "未找到当前用户的服务上下文。",
                    ["ask_user_to_login_or_verify"],
                    allowed=False,
                )

            cursor.execute(
                """
                SELECT order_id, order_status, created_at
                FROM orders
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 3
                """,
                (user_id,),
            )
            recent_orders = cursor.fetchall()

        membership = {
            "member_level": user.pop("member_level", None) or "Standard",
            "points": user.pop("points", 0),
            "growth_value": user.pop("growth_value", 0),
        }
        service_context = {
            "identity": {
                "user_id": user["user_id"],
                "display_name": user["display_name"],
                "account_status": user["account_status"],
                "authenticated": True,
                "scope": "self",
            },
            "preferences": {
                "preferred_language": user["preferred_language"],
            },
            "membership": membership,
            "contact_hints": {
                "phone_masked": user.get("phone_masked"),
                "email_masked": user.get("email_masked"),
                "full_contact_hidden": True,
            },
            "recent_order_hint": recent_orders[0]["order_id"] if recent_orders else None,
            "recent_orders": [
                {
                    "order_id": order["order_id"],
                    "order_status": order["order_status"],
                    "created_at": order["created_at"],
                }
                for order in recent_orders
            ],
        }
        return {
            "tool": self.name,
            "status": "success",
            "data": jsonable(service_context),
            "display_summary": f"已获取用户 {service_context['identity']['display_name']} 的基础服务上下文。",
            "suggested_next_actions": ["use_context_for_service"],
            "permission": {
                "checked": True,
                "allowed": True,
                "resource": "user_context",
                "scope": "self",
                "user_id": user_id,
            },
        }


class OrderLookupTool:
    name = "order.lookup"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        order_id = str(arguments.get("order_id") or "").strip()
        user_id = str(arguments.get("user_id") or "").strip()

        with connection.cursor() as cursor:
            order, failure = _fetch_owned_order(
                cursor,
                tool=self.name,
                order_id=order_id,
                user_id=user_id,
            )
            if failure:
                return failure

            cursor.execute(
                """
                SELECT product_name, sku_name, quantity, unit_price
                FROM order_items
                WHERE order_id = %s
                ORDER BY id
                """,
                (order_id,),
            )
            items = cursor.fetchall()
            cursor.execute(
                """
                SELECT logistics_status, carrier, tracking_number,
                       estimated_delivery_time, last_update
                FROM shipments
                WHERE order_id = %s
                """,
                (order_id,),
            )
            shipment = cursor.fetchone()

        order["items"] = items
        if shipment:
            order.update(shipment)
        return {
            "tool": self.name,
            "status": "success",
            "data": jsonable(order),
            "display_summary": order_summary(order),
            "suggested_next_actions": ["reply_to_user", "offer_handoff_if_user_is_unsatisfied"],
            "permission": _permission_ok("order", order_id),
        }


class ShipmentLookupTool:
    name = "shipment.lookup"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        order_id = str(arguments.get("order_id") or "").strip()
        user_id = str(arguments.get("user_id") or "").strip()

        with connection.cursor() as cursor:
            order, failure = _fetch_owned_order(
                cursor,
                tool=self.name,
                order_id=order_id,
                user_id=user_id,
            )
            if failure:
                return failure

            cursor.execute(
                """
                SELECT logistics_status, carrier, tracking_number,
                       estimated_delivery_time, last_update, shipped_at, delivered_at
                FROM shipments
                WHERE order_id = %s
                """,
                (order_id,),
            )
            shipment = cursor.fetchone()

        if not shipment:
            return failed_result(
                self.name,
                "not_found",
                "该订单暂无物流记录。",
                ["reply_to_user", "human_handoff_if_needed"],
                allowed=True,
                data={"order_id": order_id, "order_status": order["order_status"]},
            )

        shipment["order_id"] = order_id
        shipment["order_status"] = order["order_status"]
        return {
            "tool": self.name,
            "status": "success",
            "data": jsonable(shipment),
            "display_summary": (
                f"订单 {order_id} 当前物流状态为 {shipment['logistics_status']}，"
                f"最近更新：{shipment.get('last_update') or '暂无'}。"
            ),
            "suggested_next_actions": ["reply_to_user", "offer_handoff_if_user_is_unsatisfied"],
            "permission": _permission_ok("shipment", order_id),
        }


class PaymentLookupTool:
    name = "payment.lookup"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        order_id = str(arguments.get("order_id") or "").strip()
        user_id = str(arguments.get("user_id") or "").strip()

        with connection.cursor() as cursor:
            order, failure = _fetch_owned_order(
                cursor,
                tool=self.name,
                order_id=order_id,
                user_id=user_id,
            )
            if failure:
                return failure

            cursor.execute(
                """
                SELECT payment_status, payment_method, paid_amount,
                       transaction_id, paid_at
                FROM payments
                WHERE order_id = %s
                """,
                (order_id,),
            )
            payment = cursor.fetchone()

        if not payment:
            return failed_result(
                self.name,
                "not_found",
                "该订单暂无支付记录。",
                ["reply_to_user", "human_handoff_if_needed"],
                allowed=True,
                data={"order_id": order_id, "order_status": order["order_status"]},
            )

        payment["order_id"] = order_id
        payment["order_status"] = order["order_status"]
        payment["transaction_id_masked"] = _mask_transaction_id(payment.pop("transaction_id", None))
        return {
            "tool": self.name,
            "status": "success",
            "data": jsonable(payment),
            "display_summary": (
                f"订单 {order_id} 支付状态为 {payment['payment_status']}，"
                f"支付方式为 {payment['payment_method']}。"
            ),
            "suggested_next_actions": ["reply_to_user", "human_handoff_if_payment_dispute"],
            "permission": _permission_ok("payment", order_id),
        }


class AfterSalesLookupTool:
    name = "after_sales.lookup"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        order_id = str(arguments.get("order_id") or "").strip()
        user_id = str(arguments.get("user_id") or "").strip()

        with connection.cursor() as cursor:
            order, failure = _fetch_owned_order(
                cursor,
                tool=self.name,
                order_id=order_id,
                user_id=user_id,
            )
            if failure:
                return failure

            cursor.execute(
                """
                SELECT after_sales_id, service_type, status, reason,
                       created_at, updated_at
                FROM after_sales
                WHERE order_id = %s AND user_id = %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (order_id, user_id),
            )
            cases = cursor.fetchall()

        return {
            "tool": self.name,
            "status": "success",
            "data": {
                "order_id": order_id,
                "order_status": order["order_status"],
                "after_sales": jsonable(cases),
            },
            "display_summary": (
                f"订单 {order_id} 找到 {len(cases)} 条售后记录。"
                if cases
                else f"订单 {order_id} 暂无售后记录。"
            ),
            "suggested_next_actions": ["reply_to_user", "create_ticket_if_needed"],
            "permission": _permission_ok("after_sales", order_id),
        }


class TicketCreateTool:
    name = "ticket.create"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        user_id = str(arguments.get("user_id") or "").strip()
        conversation_id = str(arguments.get("conversation_id") or "").strip()
        title = str(arguments.get("title") or "客服跟进工单").strip()
        description = str(arguments.get("description") or "").strip()
        priority = str(arguments.get("priority") or "normal").strip()
        case_type = str(arguments.get("case_type") or "feedback").strip()
        related_order_id = arguments.get("related_order_id")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tickets (
                    user_id, conversation_id, case_type, title, description,
                    priority, status, related_order_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'created', %s)
                """,
                (
                    user_id or None,
                    conversation_id or None,
                    case_type,
                    title,
                    description,
                    priority,
                    related_order_id,
                ),
            )
            numeric_id = cursor.lastrowid
            ticket_id = f"TK-{numeric_id:06d}"
            cursor.execute("UPDATE tickets SET ticket_id = %s WHERE id = %s", (ticket_id, numeric_id))
            cursor.execute(
                """
                INSERT INTO ticket_events (ticket_id, event_type, content)
                VALUES (%s, 'created', %s)
                """,
                (ticket_id, "工单已由智能客服创建。"),
            )

        return {
            "tool": self.name,
            "status": "success",
            "data": {
                "ticket_id": ticket_id,
                "title": title,
                "status": "created",
                "priority": priority,
                "case_type": case_type,
            },
            "display_summary": f"已创建工单 {ticket_id}，客服会根据记录继续跟进。",
            "suggested_next_actions": ["reply_to_user", "offer_handoff_if_urgent"],
            "permission": {"checked": True, "allowed": True},
        }


class HandoffRequestTool:
    name = "handoff.request"
    requires_database = True

    def run(
        self,
        arguments: dict[str, Any],
        context: CustomerServiceMCPContext,
    ) -> dict[str, Any]:
        connection = require_connection(context)
        user_id = str(arguments.get("user_id") or "").strip()
        conversation_id = str(arguments.get("conversation_id") or "").strip()
        reason = str(arguments.get("reason") or "user_requested_human").strip()
        summary = str(arguments.get("summary") or "").strip()
        priority = str(arguments.get("priority") or "normal").strip()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS waiting_count
                FROM handoff_requests
                WHERE status IN ('queued', 'assigned')
                """
            )
            waiting = int(cursor.fetchone()["waiting_count"])
            cursor.execute(
                """
                INSERT INTO handoff_requests (
                    user_id, conversation_id, reason, summary, priority,
                    status, queue_position
                )
                VALUES (%s, %s, %s, %s, %s, 'queued', %s)
                """,
                (
                    user_id or None,
                    conversation_id or None,
                    reason,
                    summary,
                    priority,
                    waiting + 1,
                ),
            )
            numeric_id = cursor.lastrowid
            handoff_id = f"HO-{numeric_id:06d}"
            cursor.execute("UPDATE handoff_requests SET handoff_id = %s WHERE id = %s", (handoff_id, numeric_id))

        return {
            "tool": self.name,
            "status": "success",
            "data": {
                "handoff_id": handoff_id,
                "reason": reason,
                "status": "queued",
                "queue_position": waiting + 1,
                "priority": priority,
            },
            "display_summary": f"已为您提交人工客服转接请求，排队编号 {handoff_id}，当前排队位置 {waiting + 1}。",
            "suggested_next_actions": ["reply_to_user"],
            "permission": {"checked": True, "allowed": True},
        }
