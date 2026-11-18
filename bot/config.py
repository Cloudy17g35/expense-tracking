"""Konfiguracja ze zmiennych środowiskowych (w GitHub Actions: sekrety repozytorium)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_token: SecretStr
    allowed_chat_id: int
    # JSON: {"<telegram_user_id>": "<imię>"}
    users: dict[int, str] = {}
