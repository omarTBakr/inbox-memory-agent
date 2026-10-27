"""feedback_items: one row per email the assistant handled (notified, replied or ignored)."""

import json
import uuid

import psycopg
from psycopg.rows import dict_row

from email_assistant.settings import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_items (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    stage text NOT NULL,
    email_ref text NOT NULL,
    email jsonb NOT NULL,
    classification text NOT NULL,
    reasoning text NOT NULL,
    notification jsonb,
    trajectory jsonb NOT NULL DEFAULT '[]',
    trace_id text,
    mlflow_run_id text,
    digest_sent boolean NOT NULL DEFAULT false,
    telegram_message_id bigint,
    prompt_message_id bigint,
    rating text,
    corrected_label text,
    comment text,
    applied jsonb NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- set when the user moved a Spam email back to the Inbox ("Not spam")
ALTER TABLE feedback_items ADD COLUMN IF NOT EXISTS moved_to_inbox boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS feedback_items_user_created ON feedback_items (user_id, created_at DESC);
"""

_JSON = {"email", "notification", "trajectory", "applied"}


def _connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True, row_factory=dict_row)


def setup() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA)


def new_id() -> str:
    # short: Telegram callback data is limited to 64 bytes
    return uuid.uuid4().hex[:12]


def create(item_id: str, **fields) -> str:
    fields = {k: json.dumps(v) if k in _JSON else v for k, v in fields.items()}
    columns = ["id", "user_id", *fields]
    values = [item_id, get_settings().app_user_id, *fields.values()]
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO feedback_items ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(values))})", values,
        )
    return item_id


def update(item_id: str, **fields) -> None:
    fields = {k: json.dumps(v) if k in _JSON else v for k, v in fields.items()}
    sets = ", ".join(f"{k} = %s" for k in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE feedback_items SET {sets}, updated_at = now() WHERE id = %s", [*fields.values(), item_id])


def get(item_id: str) -> dict | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM feedback_items WHERE id = %s", (item_id,)).fetchone()


def by_prompt_message(message_id: int) -> dict | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM feedback_items WHERE user_id = %s AND prompt_message_id = %s",
            (get_settings().app_user_id, message_id),
        ).fetchone()


def by_message(telegram_message_id: int) -> list[dict]:
    """Feedback rows shown in one Telegram message (one notification, or every email of a digest)."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM feedback_items WHERE user_id = %s AND telegram_message_id = %s ORDER BY created_at",
            (get_settings().app_user_id, telegram_message_id),
        ).fetchall()


def recent(limit: int, offset: int = 0) -> list[dict]:
    with _connect() as conn:
        return conn.execute(
            "SELECT id, created_at, stage, email_ref, email, classification, reasoning, notification, "
            "rating, corrected_label, comment, applied, digest_sent, trace_id, moved_to_inbox FROM feedback_items "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (get_settings().app_user_id, limit, offset),
        ).fetchall()


def pending_digest() -> list[dict]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM feedback_items WHERE user_id = %s AND classification = 'ignore' AND NOT digest_sent "
            "ORDER BY created_at",
            (get_settings().app_user_id,),
        ).fetchall()


def stats(mlflow_run_id: str) -> dict:
    with _connect() as conn:
        return conn.execute(
            "SELECT count(*) FILTER (WHERE rating = 'up') AS up, count(*) FILTER (WHERE rating = 'down') AS down "
            "FROM feedback_items WHERE mlflow_run_id = %s",
            (mlflow_run_id,),
        ).fetchone()
