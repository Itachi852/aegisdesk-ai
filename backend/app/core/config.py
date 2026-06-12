from pathlib import Path
from urllib.parse import quote_plus

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "AegisDesk AI"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    jwt_secret_key: str = "replace-this-in-production"
    access_token_expire_minutes: int = 60 * 24

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user_name: str = "root"
    mysql_user_password: str
    mysql_db_name: str = "aegisdeskai"
    redis_url: str = "redis://localhost:6379/0"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "knowledge_chunks"

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = "replace-with-your-api-key"
    llm_model: str = "qwen-plus"

    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    daily_question_limit: int = 100
    max_question_length: int = 500
    rag_top_k: int = 6
    rag_score_threshold: float = 0.5

    @computed_field
    @property
    def mysql_url(self) -> str:
        user = quote_plus(self.mysql_user_name)
        password = quote_plus(self.mysql_user_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db_name}?charset=utf8mb4"
        )

    @computed_field
    @property
    def resolved_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.llm_base_url

    @computed_field
    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")


settings = Settings()
