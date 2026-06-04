from dataclasses import dataclass
import json
import re

from app.agent.actions import (
    AgentAction,
    AskUserAction,
    CapabilityAction,
    FinalAnswerAction,
    LLMAction,
)
from app.agent.context import TurnContext
from app.schemas.chat import ChatRequest, ConversationState


@dataclass(frozen=True)
class MarkdownSkillDefinition:
    name: str
    description: str
    priority: int
    capabilities: list[str]
    intents: list[str]
    skill_body: str
    references: dict[str, str]


class MarkdownSkill:
    def __init__(self, definition: MarkdownSkillDefinition) -> None:
        self.name = definition.name
        self.description = definition.description
        self.priority = definition.priority
        self._definition = definition

    def can_handle(self, request: ChatRequest, state: ConversationState) -> float:
        text = request.message.lower()
        keyword_score = 0.0
        for keyword in self._keywords():
            if keyword and keyword.lower() in text:
                keyword_score += 0.15
        return min(0.95, 0.45 + keyword_score)

    async def next_action(self, context: TurnContext) -> AgentAction:
        context.state.active_skill = self.name
        context.state.active_intent = context.state.active_intent or "customer_service"
        context.state.summary = f"Latest user message: {context.request.message}"

        response_observation = context.latest_llm_observation("response_generation")
        if response_observation and response_observation.content:
            return FinalAnswerAction(answer=response_observation.content)

        capability_observation = context.latest_observation("capability")
        if capability_observation and capability_observation.data:
            follow_up = self._follow_up_after_capability(context, capability_observation.data)
            if follow_up:
                return follow_up
            return self._llm_action_with_tool_result(context, capability_observation.data)

        image_route = self._image_route(context)
        if image_route:
            self._apply_route(context, image_route)
            capability_action = self._capability_action(context, image_route)
            if capability_action:
                return capability_action

        route = self._rule_route(context.request.message)
        if not route:
            intent_observation = context.latest_llm_observation("intent_recognition")
            if not intent_observation:
                return self._intent_recognition_action(context)
            route = self._route_from_intent_observation(intent_observation.content)

        if route:
            self._apply_route(context, route)
            capability_action = self._capability_action(context, route)
            if capability_action:
                return capability_action
            fallback_action = self._fallback_action(context, route)
            if fallback_action:
                return fallback_action

        return LLMAction(
            purpose="response_generation",
            prompt=context.request.message,
            context=self._base_llm_context(context),
        )

    def _llm_action_with_tool_result(
        self,
        context: TurnContext,
        tool_result: dict,
    ) -> LLMAction:
        capability_results = [
            observation.data
            for observation in context.observations
            if observation.type == "capability" and observation.data
        ]
        return LLMAction(
            purpose="response_generation",
            prompt=(
                "请根据 MCP 工具返回结果，用中文客服话术回复用户。"
                "不要暴露内部 JSON、trace 或 mock 细节。"
                "如果有 vision.analyze 和 knowledge.search 两类结果，"
                "视觉结果只作为图片可见内容，商品是否在售、价格、参数、真假、官方发布状态"
                "必须以 knowledge.search 或商品目录结果为准。"
                "如果知识库未命中外部品牌型号，只能说本店知识库/商品目录未查到在售记录，"
                "不要声称外部品牌官方是否已经发布。"
            ),
            context={
                **self._base_llm_context(context),
                "mcp_tool_result": tool_result,
                "mcp_tool_results": capability_results,
            },
        )

    def _follow_up_after_capability(
        self,
        context: TurnContext,
        tool_result: dict,
    ) -> CapabilityAction | None:
        if tool_result.get("capability") != "vision_analyze":
            return None
        if tool_result.get("status") == "failed":
            return None
        if context.state.task_state.get("image_knowledge_checked"):
            return None
        if not self._image_question_needs_knowledge(context.request.message):
            return None
        analysis = str(tool_result.get("data", {}).get("analysis") or tool_result.get("display_summary") or "")
        query = " ".join(
            item
            for item in [
                context.request.message,
                analysis,
                "商品目录 是否在售 价格 参数 正品 本店销售",
            ]
            if item
        )
        context.state.task_state["image_knowledge_checked"] = True
        context.state.task_state["image_knowledge_query"] = query
        plan = context.state.task_state.get("structured_plan")
        if isinstance(plan, dict):
            context.state.task_state["structured_plan"] = {
                **plan,
                "next_step": "use_capability:knowledge_search",
                "fallback": {
                    "action": "knowledge_verify_image_claim",
                    "reason": "image_question_requires_catalog_fact",
                },
            }
        return CapabilityAction(
            capability="knowledge_search",
            arguments={
                "query": query,
                "user_id": context.request.user_id,
                "tenant_id": context.request.tenant_id,
                "brand_id": context.request.brand_id,
            },
        )

    def _base_llm_context(self, context: TurnContext) -> dict:
        return {
            "system_prompt": self._build_system_prompt(context),
            "conversation_state": context.state.model_dump(),
            "recent_messages": [
                message.model_dump() for message in context.state.recent_messages
            ],
            "long_term_memory": context.state.long_term_memory,
            "skill": {
                "name": self.name,
                "description": self.description,
                "capabilities": self._definition.capabilities,
                "intents": self._definition.intents,
            },
            "loaded_references": self._selected_reference_names(context),
            "available_capabilities": context.available_capabilities,
            "available_tools": context.available_tools,
            "skill_plan": context.state.task_state.get("structured_plan"),
        }

    def _build_system_prompt(self, context: TurnContext) -> str:
        parts = [
            "你正在运行一个可插拔 Agent Framework。以下内容来自当前加载的 skill。",
            "必须遵守 skill 中的角色、边界、能力请求和转人工策略。",
            self._definition.skill_body,
        ]
        for name in self._selected_reference_names(context):
            content = self._definition.references.get(name)
            if content:
                parts.append(f"\n# Reference: {name}\n{content}")
        return "\n\n".join(parts)

    def _selected_reference_names(self, context: TurnContext) -> list[str]:
        selected = [
            "persona.md",
            "conversation_policy.md",
            "intent_taxonomy.md",
            "mcp_policy.md",
            "planner_contract.md",
        ]
        explicit_references = context.state.task_state.get("selected_references")
        if isinstance(explicit_references, list):
            selected.extend(str(name) for name in explicit_references)
        text = context.request.message.lower()
        intent = str(context.state.task_state.get("recognized_intent") or "")
        conditional: list[tuple[list[str], list[str]]] = [
            (
                [
                    "订单",
                    "物流",
                    "快递",
                    "配送",
                    "派送",
                    "支付",
                    "到哪",
                    "到了",
                    "order_status",
                    "order_overview",
                    "logistics",
                    "shipment_status",
                    "payment_status",
                ],
                ["order_playbook.md", "identity_policy.md", "response_templates.md"],
            ),
            (
                [
                    "退款",
                    "退货",
                    "换货",
                    "售后",
                    "维修",
                    "补发",
                    "after_sales",
                    "after_sales_status",
                    "after_sales_policy",
                    "refund",
                ],
                ["after_sales_playbook.md", "knowledge_playbook.md", "ticket_playbook.md"],
            ),
            (
                ["商品", "价格", "活动", "优惠", "怎么买", "推荐", "适合", "pre_sales", "product_question"],
                ["pre_sales_playbook.md", "knowledge_playbook.md"],
            ),
            (
                ["规则", "政策", "faq", "怎么用", "说明", "发票", "配送范围", "knowledge", "knowledge_policy"],
                ["knowledge_playbook.md", "response_templates.md"],
            ),
            (
                ["投诉", "不满意", "赔偿", "太慢", "生气", "人工", "真人客服", "complaint", "handoff"],
                ["complaint_playbook.md", "handoff_policy.md", "ticket_playbook.md"],
            ),
            (
                ["工单", "记录", "反馈", "跟进", "回访", "ticket"],
                ["ticket_playbook.md", "handoff_policy.md"],
            ),
        ]
        for triggers, files in conditional:
            if any(trigger.lower() in text or trigger.lower() in intent for trigger in triggers):
                selected.extend(files)

        return [
            name
            for index, name in enumerate(selected)
            if name in self._definition.references and name not in selected[:index]
        ]

    def _intent_recognition_action(self, context: TurnContext) -> LLMAction:
        return LLMAction(
            purpose="intent_recognition",
            prompt=(
                "请只输出 JSON，不要输出 Markdown。根据用户消息识别客服意图。"
                "字段：intent, confidence, slots, capability, references, fallback。"
                "intent 可选：greeting, product_question, knowledge_policy, "
                "order_overview, shipment_status, payment_status, after_sales_status, "
                "after_sales_policy, image_question, complaint, handoff, ticket, "
                "identity_verification, out_of_scope, general_question。"
                "capability 可选：order_lookup, shipment_lookup, payment_lookup, "
                "after_sales_lookup, knowledge_search, vision_analyze, human_handoff, "
                "ticket_create, user_lookup 或 null。"
                "references 返回建议加载的 reference 文件名数组。"
                "fallback 包含 action 和 reason；缺少订单号时 action 为 ask_order_id。"
            ),
            context={
                "system_prompt": (
                    "你是智能客服框架中的意图识别器。你的任务是进行结构化分类，"
                    "不要回答用户问题，只输出合法 JSON。"
                ),
                "user_message": context.request.message,
                "available_capabilities": context.available_capabilities,
                "available_tools": context.available_tools,
                "recent_messages": [
                    message.model_dump() for message in context.state.recent_messages
                ],
            },
        )

    def _route_from_intent_observation(self, content: str | None) -> dict | None:
        if not content:
            return None
        parsed = self._parse_json_object(content)
        if not parsed:
            return None
        route = {
            "intent": parsed.get("intent") or "general_question",
            "capability": parsed.get("capability"),
            "references": parsed.get("references") if isinstance(parsed.get("references"), list) else [],
            "fallback": parsed.get("fallback") if isinstance(parsed.get("fallback"), dict) else {},
        }
        slots = parsed.get("slots") if isinstance(parsed.get("slots"), dict) else {}
        order_id = slots.get("order_id") or self._extract_order_id(content)
        if order_id:
            route["order_id"] = str(order_id)
        if slots:
            route["slots"] = slots
        return route

    def _rule_route(self, message: str) -> dict | None:
        order_id = self._extract_order_id(message)
        if order_id and self._looks_like_order_lookup(message):
            if self._looks_like_shipment_lookup(message):
                return {
                    "intent": "shipment_status",
                    "capability": "shipment_lookup",
                    "order_id": order_id,
                    "references": [
                        "order_playbook.md",
                        "identity_policy.md",
                        "response_templates.md",
                    ],
                }
            if self._looks_like_payment_lookup(message):
                return {
                    "intent": "payment_status",
                    "capability": "payment_lookup",
                    "order_id": order_id,
                    "references": [
                        "order_playbook.md",
                        "identity_policy.md",
                        "response_templates.md",
                    ],
                }
            if self._looks_like_after_sales_lookup(message):
                return {
                    "intent": "after_sales_status",
                    "capability": "after_sales_lookup",
                    "order_id": order_id,
                    "references": [
                        "after_sales_playbook.md",
                        "order_playbook.md",
                        "identity_policy.md",
                    ],
                }
            return {
                "intent": "order_overview",
                "capability": "order_lookup",
                "order_id": order_id,
                "references": [
                    "order_playbook.md",
                    "identity_policy.md",
                    "response_templates.md",
                ],
            }
        if any(word in message for word in ["退款", "退货", "换货", "售后", "维修", "补发"]):
            return {
                "intent": "after_sales_policy",
                "capability": "knowledge_search",
                "query": message,
                "references": ["after_sales_playbook.md", "knowledge_playbook.md"],
            }
        if any(word in message for word in ["投诉", "不满意", "赔偿", "人工", "真人客服"]):
            if any(word in message for word in ["人工", "真人客服"]):
                return {
                    "intent": "handoff",
                    "capability": "human_handoff",
                    "reason": "user_requested_human",
                    "references": ["complaint_playbook.md", "handoff_policy.md"],
                }
            return {
                "intent": "complaint",
                "capability": "ticket_create",
                "title": "用户投诉或不满反馈",
                "references": ["complaint_playbook.md", "ticket_playbook.md"],
            }
        if any(word in message for word in ["商品", "价格", "活动", "优惠", "推荐", "适合"]):
            return {
                "intent": "product_question",
                "capability": "knowledge_search",
                "query": message,
                "references": ["pre_sales_playbook.md", "knowledge_playbook.md"],
            }
        if any(word in message for word in ["规则", "政策", "faq", "怎么用", "说明", "发票", "配送范围"]):
            return {
                "intent": "knowledge_policy",
                "capability": "knowledge_search",
                "query": message,
                "references": ["knowledge_playbook.md", "response_templates.md"],
            }
        if any(word in message for word in ["会员", "我的资料", "个人信息", "账户", "账号"]):
            return {
                "intent": "identity_verification",
                "capability": "user_lookup",
                "references": ["identity_policy.md"],
            }
        if any(word in message for word in ["工单", "记录", "反馈", "跟进", "回访"]):
            return {
                "intent": "ticket",
                "capability": "ticket_create",
                "title": "用户请求创建跟进记录",
                "references": ["ticket_playbook.md"],
            }
        return None

    def _image_route(self, context: TurnContext) -> dict | None:
        images = self._request_images(context)
        if not images:
            return None
        question = context.request.message.strip() or "请帮我查看这张图片，并说明对客服处理有用的信息。"
        return {
            "intent": "image_question",
            "capability": "vision_analyze",
            "question": question,
            "images": images,
            "references": ["response_templates.md", "planner_contract.md"],
            "source": "image_context",
        }

    def _apply_route(self, context: TurnContext, route: dict) -> None:
        intent = str(route.get("intent") or "general_question")
        plan = self._structured_plan(context, route)
        context.state.active_intent = intent
        context.state.task_state["recognized_intent"] = intent
        context.state.task_state["structured_plan"] = plan
        if route.get("references"):
            context.state.task_state["selected_references"] = route["references"]
        if route.get("order_id"):
            context.state.task_state["order_id"] = route["order_id"]
        if route.get("slots"):
            context.state.task_state["slots"] = route["slots"]

    def _capability_action(self, context: TurnContext, route: dict) -> CapabilityAction | None:
        capability = route.get("capability")
        if self._requires_order_id(capability) and not route.get("order_id"):
            return None
        if capability == "order_lookup" and route.get("order_id"):
            return self._order_lookup_action(context, str(route["order_id"]))
        if capability == "shipment_lookup" and route.get("order_id"):
            return self._owned_order_action(context, "shipment_lookup", str(route["order_id"]))
        if capability == "payment_lookup" and route.get("order_id"):
            return self._owned_order_action(context, "payment_lookup", str(route["order_id"]))
        if capability == "after_sales_lookup" and route.get("order_id"):
            return self._owned_order_action(context, "after_sales_lookup", str(route["order_id"]))
        if capability == "knowledge_search":
            return CapabilityAction(
                capability="knowledge_search",
                arguments={
                    "query": str(route.get("query") or context.request.message),
                    "user_id": context.request.user_id,
                    "tenant_id": context.request.tenant_id,
                    "brand_id": context.request.brand_id,
                },
            )
        if capability == "vision_analyze":
            images = route.get("images")
            if not isinstance(images, list):
                images = self._request_images(context)
            return CapabilityAction(
                capability="vision_analyze",
                arguments={
                    "question": str(route.get("question") or context.request.message),
                    "images": images,
                    "user_id": context.request.user_id,
                    "tenant_id": context.request.tenant_id,
                    "brand_id": context.request.brand_id,
                },
            )
        if capability == "human_handoff":
            return CapabilityAction(
                capability="human_handoff",
                arguments={
                    "reason": str(route.get("reason") or "user_requested_human"),
                    "summary": context.state.summary,
                    "user_id": context.request.user_id,
                    "conversation_id": context.request.conversation_id,
                },
            )
        if capability == "ticket_create":
            return CapabilityAction(
                capability="ticket_create",
                arguments={
                    "title": str(route.get("title") or "客服跟进工单"),
                    "description": context.request.message,
                    "user_id": context.request.user_id,
                    "conversation_id": context.request.conversation_id,
                    "priority": "high" if route.get("intent") == "complaint" else "normal",
                },
            )
        if capability == "user_lookup":
            return CapabilityAction(
                capability="user_lookup",
                arguments={
                    "user_id": context.request.user_id,
                    "tenant_id": context.request.tenant_id,
                    "brand_id": context.request.brand_id,
                },
            )
        return None

    def _fallback_action(self, context: TurnContext, route: dict) -> AskUserAction | None:
        capability = route.get("capability")
        fallback = route.get("fallback") if isinstance(route.get("fallback"), dict) else {}
        if self._requires_order_id(capability) and not route.get("order_id"):
            self._update_plan_fallback(context, "ask_order_id", "missing_order_id")
            return AskUserAction(
                question="我可以帮您查询。请提供订单号，或告诉我是否查询当前账号下最近一笔订单。"
            )
        if fallback.get("action") == "ask_order_id":
            self._update_plan_fallback(context, "ask_order_id", str(fallback.get("reason") or "missing_order_id"))
            return AskUserAction(
                question="我可以帮您查询。请提供订单号，或告诉我是否查询当前账号下最近一笔订单。"
            )
        return None

    def _structured_plan(self, context: TurnContext, route: dict) -> dict:
        capability = route.get("capability")
        required_slots = self._required_slots_for_capability(capability)
        slots = route.get("slots") if isinstance(route.get("slots"), dict) else {}
        if route.get("order_id"):
            slots = {**slots, "order_id": route["order_id"]}
        if capability == "knowledge_search" and not slots.get("query"):
            slots = {**slots, "query": str(route.get("query") or context.request.message)}
        if capability == "vision_analyze" and not slots.get("image_count"):
            images = route.get("images") if isinstance(route.get("images"), list) else []
            slots = {
                **slots,
                "question": str(route.get("question") or context.request.message),
                "image_count": len(images),
            }
        if capability == "human_handoff" and not slots.get("reason"):
            slots = {**slots, "reason": str(route.get("reason") or "user_requested_human")}
        if capability == "ticket_create" and not slots.get("description"):
            slots = {**slots, "description": context.request.message}
        if capability == "user_lookup" and not slots.get("user_id"):
            slots = {**slots, "user_id": context.request.user_id}
        missing_slots = [
            slot
            for slot in required_slots
            if not slots.get(slot)
        ]
        fallback = route.get("fallback") if isinstance(route.get("fallback"), dict) else {}
        fallback_action = fallback.get("action")
        if not fallback_action and "order_id" in missing_slots:
            fallback_action = "ask_order_id"
        return {
            "version": "skill_plan.v1",
            "skill": self.name,
            "source": route.get("source") or "rule_or_intent",
            "intent": str(route.get("intent") or "general_question"),
            "capability": capability,
            "slots": slots,
            "required_slots": required_slots,
            "missing_slots": missing_slots,
            "references": route.get("references") if isinstance(route.get("references"), list) else [],
            "fallback": {
                "action": fallback_action or "default_response",
                "reason": str(fallback.get("reason") or ("missing_required_slot" if missing_slots else "none")),
            },
            "next_step": self._plan_next_step(capability, missing_slots, fallback_action),
            "user_visible": False,
        }

    def _update_plan_fallback(self, context: TurnContext, action: str, reason: str) -> None:
        plan = context.state.task_state.get("structured_plan")
        if not isinstance(plan, dict):
            return
        updated = {
            **plan,
            "fallback": {"action": action, "reason": reason},
            "next_step": action,
        }
        context.state.task_state["structured_plan"] = updated

    @staticmethod
    def _required_slots_for_capability(capability: object) -> list[str]:
        if capability in {
            "order_lookup",
            "shipment_lookup",
            "payment_lookup",
            "after_sales_lookup",
        }:
            return ["order_id"]
        if capability == "knowledge_search":
            return ["query"]
        if capability == "vision_analyze":
            return ["question", "image_count"]
        if capability == "human_handoff":
            return ["reason"]
        if capability == "ticket_create":
            return ["description"]
        if capability == "user_lookup":
            return ["user_id"]
        return []

    @staticmethod
    def _requires_order_id(capability: object) -> bool:
        return capability in {
            "order_lookup",
            "shipment_lookup",
            "payment_lookup",
            "after_sales_lookup",
        }

    @staticmethod
    def _plan_next_step(
        capability: object,
        missing_slots: list[str],
        fallback_action: object,
    ) -> str:
        if missing_slots:
            if fallback_action:
                return str(fallback_action)
            return f"ask_{missing_slots[0]}"
        if capability:
            return f"use_capability:{capability}"
        return "generate_response"

    def _order_lookup_action(self, context: TurnContext, order_id: str) -> CapabilityAction:
        return self._owned_order_action(context, "order_lookup", order_id)

    def _owned_order_action(
        self,
        context: TurnContext,
        capability: str,
        order_id: str,
    ) -> CapabilityAction:
        return CapabilityAction(
            capability=capability,
            arguments={
                "order_id": order_id,
                "user_id": context.request.user_id,
                "tenant_id": context.request.tenant_id,
                "brand_id": context.request.brand_id,
                "conversation_id": context.request.conversation_id,
            },
        )

    @staticmethod
    def _request_images(context: TurnContext) -> list[str]:
        raw_images = context.request.context.get("images")
        if not isinstance(raw_images, list):
            return []
        images: list[str] = []
        for item in raw_images:
            if isinstance(item, str):
                image = item
            elif isinstance(item, dict):
                image = str(item.get("data_url") or item.get("url") or "")
            else:
                image = ""
            if image.startswith(("data:image/", "http://", "https://")):
                images.append(image)
        return images[:4]

    @staticmethod
    def _parse_json_object(content: str) -> dict | None:
        stripped = content.strip()
        if "```" in stripped:
            stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(0)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_order_id(message: str) -> str | None:
        match = re.search(r"\b\d{8,32}\b", message)
        if not match:
            return None
        return match.group(0)

    @staticmethod
    def _looks_like_order_lookup(message: str) -> bool:
        keywords = [
            "订单",
            "物流",
            "快递",
            "配送",
            "派送",
            "支付",
            "付款",
            "扣款",
            "售后",
            "退款",
            "退货",
            "换货",
            "到哪",
            "到了",
            "查一下",
            "查询",
        ]
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _looks_like_shipment_lookup(message: str) -> bool:
        keywords = ["物流", "快递", "配送", "派送", "到哪", "到了", "送达", "运单"]
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _looks_like_payment_lookup(message: str) -> bool:
        keywords = ["支付", "付款", "扣款", "付没付", "交易", "流水"]
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _looks_like_after_sales_lookup(message: str) -> bool:
        keywords = ["售后", "退款", "退货", "换货", "维修", "补发", "售后单"]
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _image_question_needs_knowledge(message: str) -> bool:
        keywords = [
            "卖",
            "买吗",
            "能买吗",
            "有吗",
            "有没有",
            "在售",
            "上架",
            "多少钱",
            "价格",
            "参数",
            "配置",
            "正品",
            "真假",
            "真的",
            "型号",
            "官方",
            "发布",
            "商品",
            "链接",
        ]
        return any(keyword in message for keyword in keywords)

    def _keywords(self) -> list[str]:
        return [
            *self._definition.capabilities,
            *self._definition.intents,
            "客服",
            "订单",
            "售后",
            "售前",
            "退款",
            "退货",
            "物流",
            "投诉",
            "人工",
            "工单",
            "咨询",
        ]
