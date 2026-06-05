from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR: Final = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    brone_username: str = "BRONE_USERNAME_PLACEHOLDER"
    brone_password: str = "BRONE_PASSWORD_PLACEHOLDER"
    brone_url: str = "https://brone.ub.ac.id/my/"
    browser_state_dir: Path = Field(default=ROOT_DIR / ".brone-browser-state")
    brone_storage_state_b64: str = ""
    brone_browser_state_archive_url: str = ""
    brone_browser_state_archive_path: Path | None = None
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
