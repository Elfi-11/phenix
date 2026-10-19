from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Lu depuis les variables d'environnement (injectées par `env_file: .env` du compose)."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


settings = Settings()
