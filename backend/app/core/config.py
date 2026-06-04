from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CS_AGENT_", env_file=".env")

    app_name: str = "Customer Service Agent"
    app_version: str = "0.1.0"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CS_AGENT_DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_KEY",
            "deepseek_key",
        ),
    )
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    qwen_vl_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CS_AGENT_QWEN_VL_API_KEY",
            "QWEN_VL_API_KEY",
            "DASHSCOPE_API_KEY",
        ),
    )
    qwen_vl_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_vl_model: str = "qwen3-vl-flash"
    llm_timeout_seconds: float = 60.0
    vision_timeout_seconds: float = 60.0
    skills_path: str = "../skills"
    memory_path: str = "memory"
    knowledge_path: str = "knowledge"
    mcp_backend: str = "mock"
    mcp_server_url: str = "http://localhost:9001"
    mcp_timeout_seconds: float = 30.0
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: SecretStr | None = None
    mysql_database: str = "customer_service_agent"
    recent_message_limit: int = 10


settings = Settings()
