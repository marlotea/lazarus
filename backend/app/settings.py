"""App settings, read from environment variables and `backend/.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
    data_dir: Path = Path("~/448-data")
    one_base_url: str = "https://openalyx.internationalbrainlab.org"
    one_cache_dir: Path = Path("~/448-data/ONE")
    ibl_fake: bool = False
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("data_dir", "one_cache_dir", mode="after")
    @classmethod
    def _expand_home(cls, v: Path) -> Path:
        return v.expanduser()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
