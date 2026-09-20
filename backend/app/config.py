from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Testimonial & Social Proof Collector"
    API_V1_STR: str = "/api"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE_NAME: str = "socialproof"
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    # ── Email / SMTP ─────────────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""          # your-gmail@gmail.com
    SMTP_PASSWORD: str = ""          # Gmail App Password (16 chars, spaces OK)
    SMTP_FROM_EMAIL: str = ""        # defaults to SMTP_USERNAME if blank
    SMTP_FROM_NAME: str = "SocialProof"
    GMAIL_ONLY: bool = False         # Enforce @gmail.com when enabled

    @property
    def is_smtp_configured(self) -> bool:
        """Returns True only when both SMTP username and password are provided."""
        return bool(
            self.SMTP_USERNAME and self.SMTP_USERNAME.strip()
            and self.SMTP_PASSWORD and self.SMTP_PASSWORD.strip()
        )

    # ── Application ──────────────────────────────────────────────────────────
    # Used to build verification/reset links inside emails.
    # In production set to your real domain, e.g. https://yourapp.com
    APP_BASE_URL: str = "http://127.0.0.1:8000"

    # ── Verification token settings ──────────────────────────────────────────
    VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 30   # link expires after 30 min
    RESEND_COOLDOWN_SECONDS: int = 60             # must wait 60 s between resends
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=[str(ENV_FILE), ".env"],
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

