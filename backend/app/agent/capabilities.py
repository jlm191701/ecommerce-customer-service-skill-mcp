from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityTool:
    capability: str
    tool_name: str
    description: str


class CapabilityResolver:
    def __init__(self, tools: list[CapabilityTool]) -> None:
        self._tools = {tool.capability: tool for tool in tools}

    def resolve(self, capability: str) -> CapabilityTool | None:
        return self._tools.get(capability)

    def describe(self) -> list[dict[str, str]]:
        return [
            {
                "capability": tool.capability,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]


def default_capability_resolver() -> CapabilityResolver:
    return CapabilityResolver(
        tools=[
            CapabilityTool(
                capability="order_lookup",
                tool_name="order.lookup",
                description="查询订单总览和商品明细。",
            ),
            CapabilityTool(
                capability="shipment_lookup",
                tool_name="shipment.lookup",
                description="查询订单物流、承运商、运单号和预计送达时间。",
            ),
            CapabilityTool(
                capability="payment_lookup",
                tool_name="payment.lookup",
                description="查询订单支付状态、支付方式和脱敏交易信息。",
            ),
            CapabilityTool(
                capability="after_sales_lookup",
                tool_name="after_sales.lookup",
                description="查询订单关联售后记录和处理状态。",
            ),
            CapabilityTool(
                capability="knowledge_search",
                tool_name="knowledge.search",
                description="检索客服 FAQ、政策、商品和服务知识。",
            ),
            CapabilityTool(
                capability="vision_analyze",
                tool_name="vision.analyze",
                description="理解用户上传的图片，提取可见文字、商品、故障现象或截图内容。",
            ),
            CapabilityTool(
                capability="human_handoff",
                tool_name="handoff.request",
                description="请求转接人工客服。",
            ),
            CapabilityTool(
                capability="ticket_create",
                tool_name="ticket.create",
                description="创建投诉、售后或跟进工单。",
            ),
            CapabilityTool(
                capability="user_lookup",
                tool_name="user.lookup",
                description="查询当前用户的基础服务上下文。",
            ),
        ]
    )
