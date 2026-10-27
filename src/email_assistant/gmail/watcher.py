"""Auto-trigger: watch Gmail for new messages and run the last stage on each one.

New messages come from Gmail's change history (users.history.list since the last seen
historyId), so only mail that arrives after the watcher is switched on is handled. They
are also checked against the configured search (`gmail.query`, plus `gmail.spam_query`
when Spam is included). Each message goes through a durable queue (`gmail_messages`):
pending -> done | error. No message is handled twice, even across restarts, and nothing
is changed in Gmail.

One watcher per database: it holds a Postgres advisory lock while it runs, so a second
API instance or `make worker` waits instead of handling the same mail again.
"""

import logging
import threading
import time
from datetime import datetime, timezone

import psycopg
from googleapiclient.errors import HttpError
from psycopg.rows import dict_row

from email_assistant import config_store
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS gmail_watch_state (
    user_id text PRIMARY KEY,
    history_id bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS gmail_messages (
    user_id text NOT NULL,
    message_id text NOT NULL,
    folder text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts int NOT NULL DEFAULT 0,
    error text,
    feedback_id text,
    classification text,
    subject text,
    found_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    PRIMARY KEY (user_id, message_id)
);
CREATE INDEX IF NOT EXISTS gmail_messages_status ON gmail_messages (user_id, status, found_at);
"""

FOLDER_LABELS = {"inbox": "INBOX", "spam": "SPAM"}


def _connect(**kwargs) -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url.get_secret_value(), autocommit=True, row_factory=dict_row,
                           **kwargs)


def setup() -> None:
    with _connect() as conn:
        conn.execute(SCHEMA)


def _user() -> str:
    return get_settings().app_user_id


# ---------- finding new messages ----------

def _history_id() -> int | None:
    with _connect() as conn:
        row = conn.execute("SELECT history_id FROM gmail_watch_state WHERE user_id = %s", (_user(),)).fetchone()
    return row["history_id"] if row else None


def _save_history_id(history_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO gmail_watch_state (user_id, history_id) VALUES (%s, %s)
               ON CONFLICT (user_id) DO UPDATE SET history_id = EXCLUDED.history_id, updated_at = now()""",
            (_user(), history_id),
        )


def _added_since(gmail, start: int, label: str) -> tuple[set[str], int]:
    """Ids of messages added under `label` since history id `start`, and the newest history id."""
    ids, latest, page = set(), start, None
    while True:
        response = gmail.users().history().list(
            userId="me", startHistoryId=start, historyTypes=["messageAdded"], labelId=label, pageToken=page,
        ).execute()
        latest = max(latest, int(response.get("historyId", start)))
        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                message = added["message"]
                if label in message.get("labelIds", [label]):
                    ids.add(message["id"])
        page = response.get("nextPageToken")
        if not page:
            return ids, latest


def _matching(gmail, query: str, spam: bool) -> set[str]:
    """Ids of recent messages matching a Gmail search (bounded: new mail is always recent)."""
    response = gmail.users().messages().list(
        userId="me", q=query, maxResults=100, includeSpamTrash=spam,
    ).execute()
    return {m["id"] for m in response.get("messages", [])}


def find_new(gmail, cfg) -> dict[str, str]:
    """{message id: folder} for new messages matching the configured searches.

    The first call only records where Gmail's history is now: mail that was already
    there when the watcher started is left alone.
    """
    folders = {"inbox": cfg.query, **({"spam": cfg.spam_query} if cfg.include_spam else {})}
    start = _history_id()
    if start is None:
        _save_history_id(int(gmail.users().getProfile(userId="me").execute()["historyId"]))
        return {}
    found, latest = {}, start
    try:
        for folder, query in folders.items():
            added, newest = _added_since(gmail, start, FOLDER_LABELS[folder])
            latest = max(latest, newest)
            if added:
                found.update({i: folder for i in added & _matching(gmail, query, folder == "spam")})
    except HttpError as e:
        if e.resp.status != 404:
            raise
        # history expired (kept about a week): catch up on recent mail, then restart from now
        log.warning("Gmail history %s expired; catching up with a search", start)
        fallback = get_settings().gmail_history_fallback_query
        for folder, query in folders.items():
            found.update({i: folder for i in _matching(gmail, f"{query} {fallback}", folder == "spam")})
        latest = int(gmail.users().getProfile(userId="me").execute()["historyId"])
    _save_history_id(latest)
    return found


# ---------- the queue ----------

def enqueue(found: dict[str, str]) -> int:
    """Queue new message ids; ids seen before (any status) are ignored. Returns how many were new."""
    if not found:
        return 0
    with _connect() as conn:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO gmail_messages (user_id, message_id, folder) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            [(_user(), i, folder) for i, folder in found.items()],
        )
        return max(cur.rowcount, 0)


def pending(limit: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT message_id FROM gmail_messages WHERE user_id = %s AND status IN ('pending', 'error') "
            "AND attempts < %s ORDER BY found_at LIMIT %s",
            (_user(), get_settings().gmail_max_attempts, limit),
        ).fetchall()
    return [r["message_id"] for r in rows]


def mark(message_id: str, status: str, **fields) -> None:
    sets = ", ".join(f"{k} = %s" for k in fields)
    with _connect() as conn:
        conn.execute(
            f"UPDATE gmail_messages SET status = %s, attempts = attempts + 1, processed_at = now()"
            f"{', ' + sets if sets else ''} WHERE user_id = %s AND message_id = %s",
            [status, *fields.values(), _user(), message_id],
        )


def recent(limit: int = 10) -> list[dict]:
    with _connect() as conn:
        return conn.execute(
            "SELECT message_id, folder, status, attempts, error, feedback_id, classification, subject, found_at, "
            "processed_at FROM gmail_messages WHERE user_id = %s ORDER BY found_at DESC LIMIT %s",
            (_user(), limit),
        ).fetchall()


def counts_today() -> dict:
    with _connect() as conn:
        return conn.execute(
            "SELECT count(*) FILTER (WHERE status = 'done') AS done, count(*) FILTER (WHERE status = 'error') AS errors, "
            "count(*) FILTER (WHERE status = 'pending') AS pending FROM gmail_messages "
            "WHERE user_id = %s AND found_at >= date_trunc('day', now())",
            (_user(),),
        ).fetchone()


# ---------- one check ----------

def process(ids: list[str], gmail=None) -> list[dict]:
    """Run the last stage on these messages and record the outcome of each."""
    from email_assistant.gmail.messages import fetch
    from email_assistant.stage_runner import run
    from email_assistant.stages import STAGES

    rows = []
    for message_id in ids:  # one at a time: a failing email doesn't hold up the others
        try:
            sample = fetch([message_id], gmail)[0]
            row = run(list(STAGES)[-1], [sample])[0]
        except Exception as e:
            log.warning("Gmail watcher: %s failed: %s", message_id, e)
            mark(message_id, "error", error=f"{type(e).__name__}: {e}"[:500])
            continue
        mark(message_id, "done", feedback_id=row.get("feedback_id"), classification=row["classification"],
             subject=sample.email["subject"][:300], error=None)
        rows.append(row)
    return rows


def check_once() -> dict:
    """Find new mail, queue it, and handle up to `max_per_tick` queued messages."""
    from email_assistant.gmail.client import get_service

    cfg = config_store.section("gmail")
    gmail = get_service()
    new = enqueue(find_new(gmail, cfg))
    rows = process(pending(cfg.max_per_tick), gmail)
    return {"found": new, "processed": len(rows)}


# ---------- the background thread ----------

class Watcher:
    """Checks every `gmail.poll_seconds` while `gmail.auto_trigger` is on (read live, so the UI switch applies at once)."""

    LOCK_KEY = "email_assistant.gmail_watcher"

    def __init__(self):
        self.last_check: datetime | None = None
        self.next_check: datetime | None = None
        self.last_result: dict | None = None
        self.last_error: str | None = None
        self.has_lock = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.alive:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gmail-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def check_now(self) -> None:
        self._wake.set()

    def _wait(self, seconds: float) -> None:
        self.next_check = datetime.fromtimestamp(time.time() + seconds, timezone.utc)
        self._wake.wait(seconds)
        self._wake.clear()

    def _loop(self) -> None:
        lock_conn = None
        while not self._stop.is_set():
            cfg = None
            try:
                cfg = config_store.section("gmail")
                if not cfg.auto_trigger and not self._wake.is_set():
                    self.next_check = None
                    self._wake.wait(5)
                    continue
                self._wake.clear()
                if lock_conn is None or lock_conn.closed:
                    lock_conn = _connect()
                self.has_lock = lock_conn.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (self.LOCK_KEY,),
                ).fetchone()["ok"]
                if not self.has_lock:
                    self.last_error = "Another watcher (second API or `make worker`) is handling this mailbox."
                else:
                    self.last_result = check_once()
                    self.last_error = None
                self.last_check = datetime.now(timezone.utc)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                log.warning("Gmail watcher: %s", self.last_error)
            self._wait(cfg.poll_seconds if cfg else get_settings().gmail_poll_seconds)
        if lock_conn is not None and not lock_conn.closed:
            lock_conn.close()  # releases the advisory lock
        self.has_lock = False

    def status(self) -> dict:
        cfg = config_store.section("gmail")
        try:
            today, messages = counts_today(), recent()
        except psycopg.Error as e:
            today, messages = None, []
            self.last_error = self.last_error or str(e)
        return {
            "enabled": cfg.auto_trigger,
            "include_spam": cfg.include_spam,
            "poll_seconds": cfg.poll_seconds,
            "running": self.alive,
            "has_lock": self.has_lock,
            "last_check": self.last_check,
            "next_check": self.next_check if cfg.auto_trigger else None,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "today": today,
            "recent": messages,
        }


watcher = Watcher()
