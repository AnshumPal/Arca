from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # set to Groq URL to use free tier
    database_url: str
    app_env: str = "development"

    @property
    def async_database_url(self) -> str:
        """Ensure the URL is compatible with asyncpg.
        Handles Neon / Railway / Render connection strings which may use
        plain postgresql:// and unsupported parameters like channel_binding.
        """
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        url = self.database_url.replace(
            "postgresql://", "postgresql+asyncpg://"
        ).replace(
            "postgres://", "postgresql+asyncpg://"
        )

        # Fix query parameters — asyncpg uses ssl=require not sslmode=require
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("channel_binding", None)   # not supported by asyncpg
        if "sslmode" in params:
            params["ssl"] = params.pop("sslmode")

        fixed_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=fixed_query))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
