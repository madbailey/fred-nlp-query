from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


_ENV_KEY_MAP = {
    "FRED_API_KEY": "fred_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_KEY": "openai_api_key",
    "OPENAI_MODEL": "openai_model",
    "OPENAI_REASONING_EFFORT": "openai_reasoning_effort",
    "FRED_BASE_URL": "fred_base_url",
    "HTTP_TIMEOUT_SECONDS": "http_timeout_seconds",
}


class Settings(BaseModel):
    """Runtime configuration for the new engine."""

    model_config = ConfigDict(extra="ignore")

    fred_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    openai_reasoning_effort: str = "low"
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    http_timeout_seconds: float = 20.0


def _strip_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1]
    return value


def _load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key not in _ENV_KEY_MAP:
            continue

        values[_ENV_KEY_MAP[key]] = _strip_env_value(raw_value)

    return values


@lru_cache(maxsize=1)
def get_settings(env_file: str | Path = ".env") -> Settings:
    """Load settings from the environment, falling back to a local .env file."""

    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path

    merged_values = _load_env_file(env_path)

    for env_key, field_name in _ENV_KEY_MAP.items():
        env_value = os.getenv(env_key)
        if env_value is not None:
            merged_values[field_name] = env_value

    return Settings.model_validate(merged_values)
