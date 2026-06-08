from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./suzorako.db"
    database_url_sync: str = "sqlite:///./suzorako.db"
    debug: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
