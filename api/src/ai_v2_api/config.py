from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "AI_V2_"}

    database_url: str = "postgresql://localhost:5432/ai_v2"
    openai_api_key: str = ""
    api_secret_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]


settings = Settings()
