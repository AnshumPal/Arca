from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # set to Groq URL to use free tier
    database_url: str
    app_env: str = "development"

    @property
    def async_database_url(self) -> str:
        """Ensure the URL always uses the asyncpg driver.
        Railway (and some other providers) give a plain postgresql:// URL.
        """
        return self.database_url.replace(
            "postgresql://", "postgresql+asyncpg://"
        ).replace(
            "postgres://", "postgresql+asyncpg://"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
