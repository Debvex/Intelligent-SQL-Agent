"""Application configuration via Pydantic BaseSettings + .env."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configuration variables loaded from .env with sensible defaults."""

    # ============================================================
    # Database
    # ============================================================
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "sqlagent"
    db_user: str = "postgres"
    db_password: str = "25082005"

    # ============================================================
    # Ollama LLM
    # ============================================================
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"

    # ============================================================
    # Agent Hard Limits
    # ============================================================
    max_iterations: int = Field(default=10, ge=1, description="Max graph iterations to prevent infinite loops")
    max_retries: int = Field(default=2, ge=0, le=10, description="Max error retries before giving up")
    max_result_rows: int = Field(default=100, ge=1, description="Row limit cap on query results")
    query_timeout_seconds: int = Field(default=30, ge=1, description="Timeout for SQL execution")
    conversation_history_depth: int = Field(default=20, ge=1, description="Messages sent to LLM context window")

    # ============================================================
    # Caching
    # ============================================================
    cache_size: int = Field(default=128, ge=1, description="Max entries per session in query cache")

    # ============================================================
    # LangSmith (optional)
    # ============================================================
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "intelligent-sql-agent"

    # ============================================================
    # FastAPI
    # ============================================================
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = False


# Module-level instance (lazy usage — created on first import)
settings = Settings()

