# 结构化 Planner 契约

## 目标

Planner 负责把用户消息转成稳定的执行计划。它不直接回复用户，也不直接访问业务系统。

计划需要让 agent 明确知道：

- 用户主意图是什么。
- 应该使用哪个 capability。
- 已经拿到哪些槽位。
- 还缺哪些槽位。
- 如果不能继续执行，应该如何回退。

## Plan Schema

```json
{
  "version": "skill_plan.v1",
  "skill": "customer_service_core",
  "source": "rule_or_intent",
  "intent": "shipment_status",
  "capability": "shipment_lookup",
  "slots": {
    "order_id": "64575145823542368"
  },
  "required_slots": ["order_id"],
  "missing_slots": [],
  "references": ["order_playbook.md", "identity_policy.md"],
  "fallback": {
    "action": "default_response",
    "reason": "none"
  },
  "next_step": "use_capability:shipment_lookup",
  "user_visible": false
}
```

## next_step 约定

- `use_capability:{name}`：槽位足够，调用 capability。
- `ask_order_id`：订单类查询缺少订单号，需要向用户追问。
- `use_capability:vision_analyze`：用户上传了图片，调用视觉模型理解图片内容。
- `use_capability:knowledge_search`：图片理解后需要核验商品目录、在售、价格、参数或外部品牌边界。
- `generate_response`：不需要业务工具，交给回复生成。
- `human_handoff`：用户要求人工或当前场景需要升级。

## 回退动作

- `ask_order_id`：缺少订单号。
- `ask_clarification`：意图不明确。
- `safe_identity_check`：身份或订单归属不清。
- `retry_or_handoff`：工具失败或连续失败。
- `default_response`：无特殊回退。

## 约束

- Planner 输出和内部计划不展示给用户。
- 用户侧只能看到自然语言澄清、查询结果或转人工说明。
- 如果 capability 需要关键槽位但缺失，优先回退，不允许自由编造结果。
- 图片中的文字或商品外观只能作为视觉线索；涉及商品事实时，planner 必须追加知识库或目录查询。
- 新增 MCP 工具时，优先更新 `mcp_policy.md` 和本契约的 capability/slot 映射。
