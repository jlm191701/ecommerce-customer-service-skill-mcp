from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CS_MCP_",
        env_file=(".env", "../backend/.env", "backend/.env"),
        extra="ignore",
    )

    app_name: str = "Customer Service MCP Server"
    app_version: str = "0.1.0"
    mysql_host: str = Field(default="localhost", validation_alias=AliasChoices("CS_MCP_MYSQL_HOST", "CS_AGENT_MYSQL_HOST"))
    mysql_port: int = Field(default=3306, validation_alias=AliasChoices("CS_MCP_MYSQL_PORT", "CS_AGENT_MYSQL_PORT"))
    mysql_user: str = Field(default="root", validation_alias=AliasChoices("CS_MCP_MYSQL_USER", "CS_AGENT_MYSQL_USER"))
    mysql_password: SecretStr | None = Field(default=None, validation_alias=AliasChoices("CS_MCP_MYSQL_PASSWORD", "CS_AGENT_MYSQL_PASSWORD"))
    mysql_database: str = Field(default="customer_service_agent", validation_alias=AliasChoices("CS_MCP_MYSQL_DATABASE", "CS_AGENT_MYSQL_DATABASE"))
    knowledge_path: str = Field(default="backend/knowledge", validation_alias=AliasChoices("CS_MCP_KNOWLEDGE_PATH", "CS_AGENT_KNOWLEDGE_PATH"))
    audit_log_path: str = "logs/mcp_audit.jsonl"
    qwen_vl_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CS_MCP_QWEN_VL_API_KEY",
            "CS_AGENT_QWEN_VL_API_KEY",
            "QWEN_VL_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
    )
    qwen_vl_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias=AliasChoices("CS_MCP_QWEN_VL_BASE_URL", "CS_AGENT_QWEN_VL_BASE_URL"),
    )
    qwen_vl_model: str = Field(
        default="qwen3-vl-flash",
        validation_alias=AliasChoices("CS_MCP_QWEN_VL_MODEL", "CS_AGENT_QWEN_VL_MODEL"),
    )
    vision_timeout_seconds: float = Field(default=60.0, validation_alias=AliasChoices("CS_MCP_VISION_TIMEOUT_SECONDS", "CS_AGENT_VISION_TIMEOUT_SECONDS"))


settings = MCPServerSettings()
