from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLMs
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "ollama"  # "ollama" | "cloud"
    ollama_base_url: str = "http://localhost:11434"
    strategist_model: str = "qwen2.5:14b"
    question_setter_model: str = "llama3.1:8b"
    evaluator_model: str = "qwen2.5-coder:14b"

    # Search
    tavily_api_key: str = ""

    # Database — async driver for SQLAlchemy, psycopg3 driver for LangGraph checkpointer
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/ai_guide"
    database_url_sync: str = "postgresql+psycopg://postgres:password@localhost:5432/ai_guide"

    # Checkpointer: "postgres" | "sqlite"
    checkpointer_backend: str = "postgres"

    # Twilio / WhatsApp
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
