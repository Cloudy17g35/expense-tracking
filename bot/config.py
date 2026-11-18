"""Konfiguracja ze zmiennych środowiskowych (w GitHub Actions: sekrety repozytorium)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_token: SecretStr
    allowed_chat_id: int
    # JSON: {"<telegram_user_id>": "<imię>"}
    users: dict[int, str] = {}
    # Google Sheets: bez nich bot odpowiada na komendy, ale nie zapisuje wydatków.
    sheet_id: str | None = None
    google_sa_json: SecretStr | None = None
    # Odczyt zdjęć paragonów: bez klucza bot prosi o wpis ręczny.
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"
