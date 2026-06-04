# 独立 MCP Server 分离说明

## 当前状态

客服 MCP 工具已经从 Agent 后端中分离出一个独立 HTTP MCP-compatible Server。

运行链路：

```text
frontend
  -> backend FastAPI Agent Runtime :8001
      -> Skill / Planner / Guardrail / Memory
      -> RemoteMCPGateway
          -> mcp_server :9001
              -> CustomerServiceMCPPlugin
                  -> knowledge.search
                  -> vision.analyze
                  -> user.lookup
                  -> order.lookup
                  -> shipment.lookup
                  -> payment.lookup
                  -> after_sales.lookup
                  -> ticket.create
                  -> handoff.request
```

## 接口

健康检查：

```http
GET http://localhost:9001/health
```

工具列表：

```http
GET http://localhost:9001/tools
```

调用工具：

```http
POST http://localhost:9001/tools/call
Content-Type: application/json

{
  "name": "knowledge.search",
  "arguments": {
    "query": "Aurora Phone X1 支持多少瓦快充？",
    "limit": 1
  }
}
```

返回体保持现有工具结果格式：

```json
{
  "result": {
    "tool": "knowledge.search",
    "status": "success",
    "data": {},
    "display_summary": "...",
    "suggested_next_actions": ["reply_to_user"],
    "permission": {
      "checked": true,
      "allowed": true
    }
  }
}
```

## 配置

Agent 后端切换远程 MCP：

```env
CS_AGENT_MCP_BACKEND=remote
CS_AGENT_MCP_SERVER_URL=http://localhost:9001
CS_AGENT_MCP_TIMEOUT_SECONDS=30
```

MCP Server 配置：

```env
CS_MCP_MYSQL_HOST=localhost
CS_MCP_MYSQL_PORT=3306
CS_MCP_MYSQL_USER=root
CS_MCP_MYSQL_PASSWORD=replace-with-your-mysql-password
CS_MCP_MYSQL_DATABASE=customer_service_agent
CS_MCP_KNOWLEDGE_PATH=backend/knowledge
CS_MCP_QWEN_VL_API_KEY=replace-with-your-qwen-vl-key
CS_MCP_QWEN_VL_MODEL=qwen3-vl-flash
CS_MCP_QWEN_VL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果没有 `CS_MCP_*`，MCP Server 会兼容读取已有 `CS_AGENT_*` 配置。

## 启动

从项目根目录启动 MCP Server：

```bash
backend/.venv/Scripts/python.exe -m uvicorn mcp_server.app.main:app --host 0.0.0.0 --port 9001
```

启动 Agent 后端：

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

启动前端：

```bash
cd frontend
npm run dev
```

## 边界

- Skill 不直接访问数据库、知识库或视觉模型。
- Agent 后端只知道 capability 和 MCP gateway。
- `RemoteMCPGateway` 只负责 HTTP 调用和远程失败回退。
- MCP Server 负责工具执行、审计、数据库访问、知识检索和视觉模型调用。
- 工具结果格式保持与原内部插件一致，因此前端和 Skill 不需要知道工具是否远程。

## 后续升级

当前是 HTTP MCP-compatible Server，适合先完成工程分离。

后续可以继续升级：

1. 增加工具 schema discovery，返回参数、权限级别和失败动作。
2. 增加 server token 或签名校验。
3. 增加请求限流、超时和熔断。
4. 增加标准 MCP SDK 的 stdio / SSE / streamable HTTP 传输。
5. 将工具包发布为独立 Python 包，Agent 后端只依赖远程协议。
