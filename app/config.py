from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str

    # Security
    api_secret_key: str
    revalidation_secret: str

    # Next.js ISR
    nextjs_revalidate_url: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    operator_email: str = ""

    # Google Sheets
    google_service_account_json: str = ""
    google_sheets_spreadsheet_id: str = ""

    # App
    environment: str = "production"
    cors_origins: list[str] = [
        "https://affra-reseaux.fr",
        "https://www.affra-reseaux.fr",
        "http://localhost:8080",
        "http://localhost:3001",
    ]

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Railway often provides postgresql://...; force async SQLAlchemy driver.
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()
