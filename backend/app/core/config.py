from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: tuple[str, ...] = (
        "image/jpeg", "image/png", "image/webp",
    )
    STORAGE_ROOT: str = "storage"
    DEFAULT_THRESHOLD: float = 0.7  # unused now but harmless
    MAX_FILES_PER_BATCH: int = 5000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]