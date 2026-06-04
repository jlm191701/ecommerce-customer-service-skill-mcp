# MCP 能力与工具设计

## 目标

智能客服 skill 不直接依赖具体 MCP 工具名，而是请求稳定的业务能力。框架通过 capability resolver 将能力映射到当前可用的 MCP 工具。

这样可以做到：

- skill 只关心“需要什么能力”。
- MCP 负责“如何执行能力”。
- 后续从 mock 切换真实数据库、业务系统或第三方客服系统时，尽量不改 skill。

## 能力分层

### 查询类 Query

查询类能力只读取信息，不产生业务副作用。

| Capability | 说明 | 当前 MCP Tool | 真实接入来源 |
| --- | --- | --- | --- |
| `knowledge_search` | 查询 FAQ、政策、商品说明、服务规则 | `knowledge.search` | 知识库、文档检索、RAG、商品/政策文档 |
| `user_context_lookup` | 查询当前用户服务上下文 | `user.lookup` | 用户系统、会员系统、登录态、CRM |
| `order_status_lookup` | 查询订单总览和商品明细 | `order.lookup` | 订单系统 |
| `shipment_lookup` | 查询订单物流状态 | `shipment.lookup` | 物流系统、仓配系统 |
| `payment_lookup` | 查询订单支付状态 | `payment.lookup` | 支付系统 |
| `after_sales_lookup` | 查询订单售后记录 | `after_sales.lookup` | 售后系统 |

### 动作类 Action

动作类能力会产生业务记录、转接或其他副作用，必须由 MCP 做权限校验和审计。

| Capability | 说明 | 当前 MCP Tool | 真实接入来源 |
| --- | --- | --- | --- |
| `case_create` | 创建客服案件、投诉、售后或跟进记录 | `ticket.create` | 工单系统、客服案件系统、售后系统 |
| `human_handoff` | 请求实时转人工 | `handoff.request` | 坐席系统、客服会话平台、IM/工单系统 |

## 命名调整

当前 mock 中已有这些能力：

| 当前 Capability | 建议新 Capability | 原因 |
| --- | --- | --- |
| `user_lookup` | `user_context_lookup` | 强调查的是服务上下文，不是任意用户数据 |
| `order_lookup` | `order_status_lookup` | 强调查订单状态、支付、物流、售后状态 |
| `ticket_create` | `case_create` | 不绑定具体工单系统，适配投诉、售后、跟进等客服案件 |
| `knowledge_search` | `knowledge_search` | 语义清晰，保持不变 |
| `human_handoff` | `human_handoff` | 语义清晰，保持不变 |

MCP tool 名可以暂时保持：

```text
knowledge_search      -> knowledge.search
user_context_lookup   -> user.lookup
order_status_lookup   -> order.lookup
shipment_lookup       -> shipment.lookup
payment_lookup        -> payment.lookup
after_sales_lookup    -> after_sales.lookup
case_create           -> ticket.create
human_handoff         -> handoff.request
```

## 能力边界

### knowledge_search

用于通用知识和政策，不查询个人业务状态。

适用：

- 退货规则是什么？
- 发票怎么开？
- 配送范围有哪些？
- 商品怎么使用？
- 活动规则是什么？

不适用：

- 我的退款到哪了？
- 我的订单什么时候到？
- 我能不能退这笔订单？

这些需要结合 `order_status_lookup` 或 `user_context_lookup`。

### user_context_lookup

用于查询当前用户的服务上下文。

适用：

- 用户身份上下文。
- 会员等级。
- 最近订单提示。
- 可用联系方式提示。
- 用户服务标签。

不适用：

- 查询任意用户资料。
- 返回完整敏感个人信息。
- 绕过登录或权限校验。

当前返回边界：

- 返回 `identity`，说明当前登录用户、展示名、账号状态和 `scope=self`。
- 返回 `membership`，用于客服判断会员等级和基础权益。
- 返回 `contact_hints`，只包含脱敏手机号、脱敏邮箱和 `full_contact_hidden=true`。
- 返回 `recent_order_hint` 和最近订单状态提示，不返回地址、完整联系方式、密码或任意其他用户资料。

### order_status_lookup

用于查询具体订单总览和商品明细。

适用：

- 订单状态。
- 订单金额。
- 下单、支付、完成时间。
- 订单商品明细。

要求：

- 必须有订单 ID，或通过用户上下文找到明确订单。
- MCP 必须校验当前用户是否有权限查询该订单。

### shipment_lookup / payment_lookup / after_sales_lookup

这三个能力是从 `order_status_lookup` 中拆出来的安全子能力。

适用：

- `shipment_lookup`：物流状态、承运商、运单号、预计送达、最近物流更新。
- `payment_lookup`：支付状态、支付方式、支付金额、脱敏交易流水。
- `after_sales_lookup`：售后单号、服务类型、处理状态、原因和更新时间。

共同要求：

- 必须复用订单归属校验。
- 不允许通过订单号查询他人订单信息。
- 不返回超出工具职责范围的敏感字段。
- 支付流水、联系方式、地址等敏感信息必须脱敏或省略。

### case_create

用于创建异步客服案件。

适用：

- 投诉。
- 售后跟进。
- 物流异常。
- 用户反馈。
- 需要后续回访或人工处理但不一定实时接入。

建议参数：

```json
{
  "user_id": "string",
  "conversation_id": "string",
  "case_type": "complaint | after_sales | logistics | feedback | other",
  "title": "string",
  "description": "string",
  "priority": "low | normal | high | urgent",
  "related_order_id": "string | null"
}
```

### human_handoff

用于实时转人工。

适用：

- 用户明确要求人工。
- 强烈不满或高风险场景。
- 权限冲突。
- 工具连续失败。
- 涉及赔付、政策例外、法律或敏感信息。

建议参数：

```json
{
  "user_id": "string",
  "conversation_id": "string",
  "reason": "user_requested_human | strong_dissatisfaction | tool_failure | policy_exception | permission_conflict | high_risk",
  "summary": "string",
  "priority": "normal | high | urgent"
}
```

## Skill 使用原则

skill 不应该写死 MCP 工具名。

推荐：

```json
{
  "type": "capability",
  "capability": "order_status_lookup",
  "arguments": {
    "order_id": "64575145823542368"
  }
}
```

不推荐：

```json
{
  "type": "mcp_tool",
  "tool_name": "order.lookup",
  "arguments": {
    "order_id": "64575145823542368"
  }
}
```

如果能力不存在，框架返回 `missing_capability`，skill 应向用户说明当前还没有接入相关能力，并提供替代路径。

## 建议真实接入顺序

1. `knowledge_search`
   - 风险最低，最容易真实化。
   - 可以先接本地 Markdown 知识库或向量检索。

2. `user_context_lookup`
   - 为权限、身份、最近订单提示打基础。
   - 后续订单和工单能力都依赖它。

3. `order_status_lookup` / `shipment_lookup` / `payment_lookup` / `after_sales_lookup`
   - 接真实订单、物流、支付、售后。
   - 必须做好用户权限校验。

4. `case_create`
   - 接客服案件/工单系统。
   - 需要审计和状态追踪。

5. `human_handoff`
   - 接实时坐席系统。
   - 依赖会话平台、队列、人工接入状态。

## 真实 MCP 返回契约

建议所有 MCP 工具保持统一返回结构：

```json
{
  "tool": "order.lookup",
  "status": "success | failed",
  "data": {},
  "display_summary": "面向客服/用户可解释的摘要",
  "suggested_next_actions": ["reply_to_user"],
  "permission": {
    "checked": true,
    "allowed": true
  },
  "error_code": null
}
```

## 审计日志

MCP plugin 层记录轻量审计日志，默认写入：

```text
backend/logs/mcp_audit.jsonl
```

审计字段：

- `trace_id`：由 AgentRuntime 注入，用于串联一次对话链路。
- `conversation_id` / `user_id`：定位调用上下文。
- `tool` / `status` / `error_code`：定位工具结果。
- `duration_ms`：定位慢调用。
- `arguments`：参数摘要，不保存完整敏感值。
- `permission`：权限检查摘要，例如 `allowed=false`、`resource=payment`。

审计原则：

- 审计失败不能影响客服主流程。
- 不记录完整密码、token、交易流水、手机号、邮箱、地址。
- 对支付、订单、用户上下文等敏感工具，优先记录资源类型和权限结果，而不是完整业务数据。

失败时：

```json
{
  "tool": "order.lookup",
  "status": "failed",
  "error_code": "permission_denied | missing_argument | not_found | upstream_error",
  "display_summary": "无法查询该订单，请确认身份或订单号。",
  "suggested_next_actions": ["ask_user_for_verification", "human_handoff"],
  "permission": {
    "checked": true,
    "allowed": false
  }
}
```

## 后续实现任务

- 将当前 capability 名称迁移为新命名。
- 将 mock gateway 拆成 mock MCP server 或可替换 adapter。
- 为每个 capability 定义参数 schema。
- 为 `missing_capability` 增加用户友好的 skill 回复。
- 接入第一个真实工具：`knowledge_search`。
