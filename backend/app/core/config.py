from urllib.parse import quote_plus

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    qdrant_collection: str = "knowledge_chunks"

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = "replace-with-your-api-key"
    llm_model: str = "qwen-plus"

    embedding_model: str = "BAAI/bge-m3"
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
