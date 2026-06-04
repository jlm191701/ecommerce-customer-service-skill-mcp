# 意图分类体系

## 一级意图

智能客服先判断用户处于哪类服务场景：

- `greeting`：问候、自我介绍、能力询问。
- `product_question`：商品参数、价格、活动、购买建议、适配性。
- `knowledge_policy`：价保、发票、配送范围、退换货规则、FAQ、服务说明。
- `order_overview`：订单是否存在、订单整体状态、订单里买了什么。
- `shipment_status`：物流、快递、配送、派送、预计送达、运单状态。
- `payment_status`：支付、付款、扣款、交易流水、支付失败。
- `after_sales_status`：具体订单的退款、退货、换货、维修、补发进度。
- `after_sales_policy`：不绑定具体订单的售后政策咨询。
- `image_question`：用户上传图片，要求识别商品、截图、故障、凭证、包装或其他可见信息。
- `complaint`：投诉、不满、催促、要求赔付、负面情绪。
- `identity_verification`：身份不足、订单归属不明确、权限冲突。
- `handoff`：用户要求人工或系统判断需要人工。
- `out_of_scope`：非客服范围请求。

## 路由原则

- 有订单号时，优先判断用户问的是订单总览、物流、支付还是售后进度。
- 没有订单号但问政策、商品、价保、FAQ 时，优先 `knowledge_policy` 或 `product_question`。
- 用户表达强烈不满或明确要求人工时，优先 `complaint` 或 `handoff`。
- 用户只说“查一下”“帮我看看”但缺少对象时，先澄清。
- 一句话包含多个任务时，先处理最明确、最阻塞、风险最高的一项。

## Capability 映射

| 意图 | 首选 capability | 必要槽位 |
| --- | --- | --- |
| `product_question` | `knowledge_search` | `query` |
| `knowledge_policy` | `knowledge_search` | `query` |
| `image_question` | `vision_analyze` | `question`, `images` |
| `order_overview` | `order_lookup` | `order_id` |
| `shipment_status` | `shipment_lookup` | `order_id` |
| `payment_status` | `payment_lookup` | `order_id` |
| `after_sales_status` | `after_sales_lookup` | `order_id` |
| `after_sales_policy` | `knowledge_search` | `query` |
| `identity_verification` | `user_lookup` | `user_id` |
| `complaint` | `ticket_create` 或 `human_handoff` | `description` |
| `handoff` | `human_handoff` | `reason` |

## 缺失槽位

常见槽位：

- 订单相关：`order_id`、商品、收货人、时间范围。
- 用户相关：`user_id`、手机号后几位、会员号、渠道身份。
- 售后相关：问题类型、商品状态、退款/退货原因、期望处理方式。
- 工单相关：问题描述、联系方式、期望回复时间、附件或凭证。

缺少槽位时，一次只问一个最关键问题。

## 回退优先级

1. 缺订单号：请求订单号，或询问是否查询最近订单。
2. 权限不足：说明当前身份无法核验归属，请用户补充安全信息或转人工。
3. 记录不存在：请用户确认订单号、账号或购买渠道。
4. 工具失败：建议稍后重试；连续失败或用户着急时转人工。
5. 意图不明确：用一个问题澄清用户想查什么。
