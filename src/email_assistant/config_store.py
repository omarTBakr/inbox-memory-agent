"""UI-saved configuration in Postgres.

- app_config: one row per (user, section), validated by config_models.SECTIONS
- app_config_history: every saved version
- app_secrets: secrets encrypted with APP_ENCRYPTION_KEY (Fernet)

`section()` / `secret()` are what the rest of the app calls: they return the saved
value, or fall back to config/user_profile.yml and .env when nothing is saved yet
(or the database is unreachable), so the CLI and stages work either way.
"""

import json
import logging
import time
from typing import Any

import psycopg
import yaml
from cryptography.fernet import Fernet
from pydantic import BaseModel

from email_assistant.config_models import SECRETS, SECTIONS
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_config (
    user_id text NOT NULL,
    section text NOT NULL,
    data jsonb NOT NULL,
    version int NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, section)
);
CREATE TABLE IF NOT EXISTS app_config_history (
    user_id text NOT NULL,
    section text NOT NULL,
    version int NOT NULL,
    data jsonb NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, section, version)
);
CREATE TABLE IF NOT EXISTS app_secrets (
    user_id text NOT NULL,
    name text NOT NULL,
    ciphertext text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, name)
);
"""


def _connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True)


def _fernet() -> Fernet:
    key = get_settings().app_encryption_key.get_secret_value()
    if not key:
        raise RuntimeError("APP_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def setup() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA)


# ---------- sections ----------

def load_saved(section: str, user_id: str | None = None) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM app_config WHERE user_id = %s AND section = %s",
            (user_id or get_settings().app_user_id, section),
        ).fetchone()
    return row[0] if row else None


def save(section: str, data: dict, user_id: str | None = None) -> int:
    """Validate and save a section; returns its new version."""
    model = SECTIONS[section].model_validate(data)
    payload = json.dumps(model.model_dump(mode="json"))
    user_id = user_id or get_settings().app_user_id
    with _connect() as conn, conn.transaction():
        row = conn.execute(
            "SELECT version FROM app_config WHERE user_id = %s AND section = %s FOR UPDATE", (user_id, section),
        ).fetchone()
        version = row[0] + 1 if row else 1
        conn.execute(
            """INSERT INTO app_config (user_id, section, data, version) VALUES (%s, %s, %s, %s)
               ON CONFLICT (user_id, section) DO UPDATE SET data = EXCLUDED.data, version = EXCLUDED.version,
               updated_at = now()""",
            (user_id, section, payload, version),
        )
        conn.execute(
            "INSERT INTO app_config_history (user_id, section, version, data) VALUES (%s, %s, %s, %s)",
            (user_id, section, version, payload),
        )
    invalidate()
    return version


def saved_meta(section: str, user_id: str | None = None) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT version, updated_at FROM app_config WHERE user_id = %s AND section = %s",
            (user_id or get_settings().app_user_id, section),
        ).fetchone()
    return {"version": row[0], "updated_at": row[1].isoformat()} if row else None


def history(section: str, user_id: str | None = None) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT version, data, saved_at FROM app_config_history WHERE user_id = %s AND section = %s "
            "ORDER BY version DESC",
            (user_id or get_settings().app_user_id, section),
        ).fetchall()
    return [{"version": v, "data": d, "saved_at": t.isoformat()} for v, d, t in rows]


# ---------- secrets ----------

def set_secret(section: str, name: str, value: str, user_id: str | None = None) -> None:
    if name not in SECRETS.get(section, {}):
        raise KeyError(f"unknown secret {section}.{name}")
    token = _fernet().encrypt(value.encode()).decode()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO app_secrets (user_id, name, ciphertext) VALUES (%s, %s, %s)
               ON CONFLICT (user_id, name) DO UPDATE SET ciphertext = EXCLUDED.ciphertext, updated_at = now()""",
            (user_id or get_settings().app_user_id, f"{section}.{name}", token),
        )
    invalidate()


def delete_secret(section: str, name: str, user_id: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM app_secrets WHERE user_id = %s AND name = %s",
            (user_id or get_settings().app_user_id, f"{section}.{name}"),
        )
    invalidate()


def _load_secret(section: str, name: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT ciphertext FROM app_secrets WHERE user_id = %s AND name = %s",
            (get_settings().app_user_id, f"{section}.{name}"),
        ).fetchone()
    return _fernet().decrypt(row[0].encode()).decode() if row else None


def secret_status(section: str) -> dict[str, bool]:
    """Which of a section's secrets are set (values never leave the backend)."""
    return {name: bool(secret(section, name)) for name in SECRETS.get(section, {})}


# ---------- resolution with fallback (used by the whole app) ----------

# .env value used when a secret was never saved from the UI
_ENV_SECRETS = {
    ("notifications", "telegram_bot_token"): lambda s: s.telegram_bot_token.get_secret_value(),
}


def _yaml_profile() -> dict:
    s = get_settings()
    return yaml.safe_load(s.path(s.user_profile_path).read_text())


def yaml_section(section: str) -> dict:
    """A section as written in config/user_profile.yml (profile / notifications)."""
    if section == "profile":
        return {k: v for k, v in _yaml_profile().items() if k != "notifications"}
    return _yaml_profile().get("notifications", {})


def _fallback(section: str) -> dict:
    if section in ("profile", "notifications"):
        return yaml_section(section)
    return {}  # remaining sections take their defaults from settings


_cache: dict[tuple, tuple[float, Any]] = {}


def invalidate() -> None:
    _cache.clear()


def _cached(key: tuple, load):
    ttl = get_settings().config_cache_seconds
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = load()
    _cache[key] = (time.monotonic(), value)
    return value


def raw_section(section: str) -> tuple[dict, str]:
    """(data, source) where source is 'saved' or 'default'."""

    def load():
        try:
            saved = load_saved(section)
        except psycopg.Error as e:
            log.warning("Config DB unavailable, using defaults for %s: %s", section, e)
            saved = None
        return (saved, "saved") if saved is not None else (_fallback(section), "default")

    return _cached(("section", section), load)


def section(name: str) -> BaseModel:
    return SECTIONS[name].model_validate(raw_section(name)[0])


def secret(section_name: str, name: str) -> str:
    def load():
        try:
            value = _load_secret(section_name, name)
        except psycopg.Error as e:
            log.warning("Config DB unavailable, secret %s.%s from .env: %s", section_name, name, e)
            value = None
        if value is None and (section_name, name) in _ENV_SECRETS:
            value = _ENV_SECRETS[(section_name, name)](get_settings())
        return value or ""

    return _cached(("secret", section_name, name), load)
