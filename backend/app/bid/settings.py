from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = Path(__file__).resolve().parents[2]


class BidSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_ROOT / ".env"),
            str(_BACKEND / ".env"),
            ".env",
            "../.env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    slack_webhook_url: str = ""
    superadmin_email: str = "superadmin@localhost"
    superadmin_password: str = "change-me-superadmin"
    jwt_expire_hours: int = 168
    upload_dir: str = ""


@lru_cache
def get_bid_settings() -> BidSettings:
    return BidSettings()
