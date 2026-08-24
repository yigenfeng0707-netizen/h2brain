"""氢智行 H2Brain - 全局配置"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    app_name: str = "氢智行 H2Brain"
    app_env: str = "demo"
    debug: bool = True

    # 大模型 - 主用（OpenAI 兼容接口）
    llm_api_key: str = ""
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_model: str = "glm-4.6"

    # 大模型 - Fallback（主用失败后自动切换）
    llm_fallback_api_key: str = ""
    llm_fallback_base_url: str = ""
    llm_fallback_model: str = ""

    # 发布标识
    release_id: str = "development"

    # 跨域
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def llm_enabled(self) -> bool:
        """是否启用了真实 LLM 调用。"""
        return bool(self.llm_api_key and self.llm_api_key.strip())

    @property
    def llm_fallback_enabled(self) -> bool:
        """是否启用了 fallback LLM。"""
        return bool(self.llm_fallback_api_key and self.llm_fallback_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
