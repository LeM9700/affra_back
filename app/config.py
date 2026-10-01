from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" : une clé documentaire du .env (ex. GOOGLE_SHEETS_URL) ne doit pas empêcher le démarrage.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Attribution : hôtes du site (referrer interne ignoré lors de la classification)
    site_hosts: list[str] = ["affra-reseaux.fr", "localhost", "127.0.0.1"]

    # Identité vendeur imprimée sur les factures (instantané figé dans chaque facture).
    # Valeurs par défaut = mentions légales du site ; surchargeables par variables SELLER_*.
    seller_name: str = "AFFRA Réseaux"
    seller_legal_form: str = "SARL au capital de 5 000,00 €"
    seller_address_line1: str = "95 A rue de la Hase"
    seller_postal_code: str = "30900"
    seller_city: str = "Nîmes"
    seller_country: str = "France"
    seller_siret: str = "98445144300027"
    seller_vat_number: str = "FR94984451443"
    seller_rcs: str = "RCS Nîmes 984 451 443"
    seller_naf: str = "43.21A"
    seller_phone: str = "+33 7 66 30 46 87"
    seller_email: str = "affrareseaux@gmail.com"
    seller_iban: str = ""
    seller_bic: str = ""
    # Mention obligatoire pour les travaux du bâtiment (art. L243-2 C. assurances) — à renseigner.
    seller_insurance: str = ""

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

    @property
    def site_hosts_set(self) -> frozenset[str]:
        hosts = {h.strip().lower().removeprefix("www.") for h in self.site_hosts if h.strip()}
        return frozenset(hosts)

    def seller_snapshot(self) -> dict[str, str]:
        return {
            "name": self.seller_name,
            "legal_form": self.seller_legal_form,
            "address_line1": self.seller_address_line1,
            "postal_code": self.seller_postal_code,
            "city": self.seller_city,
            "country": self.seller_country,
            "siret": self.seller_siret,
            "vat_number": self.seller_vat_number,
            "rcs": self.seller_rcs,
            "naf": self.seller_naf,
            "phone": self.seller_phone,
            "email": self.seller_email,
            "iban": self.seller_iban,
            "bic": self.seller_bic,
            "insurance": self.seller_insurance,
        }


settings = Settings()
