"""Persistent memory in PostgreSQL.

- store: long-term memory (semantic / episodic / procedural), pgvector index for search
- checkpointer: per-thread graph state
Both are context managers because they own a database connection.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from email_assistant import config_store
from email_assistant.llm import embeddings_config, get_embeddings
from email_assistant.settings import get_settings

# config["configurable"] key holding the user id; langmem tools read the same key
USER_ID_KEY = "langgraph_user_id"


@contextmanager
def get_store() -> Iterator[PostgresStore]:
    s = get_settings()
    index = {"dims": embeddings_config().dims, "embed": get_embeddings()}
    with PostgresStore.from_conn_string(s.database_url.get_secret_value(), index=index) as store:
        yield store


@contextmanager
def get_checkpointer() -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(get_settings().database_url.get_secret_value()) as saver:
        yield saver


def namespace(*parts: str) -> tuple[str, ...]:
    """Namespace for one kind of memory, e.g. namespace("semantic", user_id)."""
    return (get_settings().memory_namespace, *parts)


def setup_database() -> None:
    """Create (or migrate) the config, feedback, Gmail queue, store and checkpointer tables."""
    from email_assistant.feedback import store as feedback_store
    from email_assistant.gmail import watcher

    config_store.setup()
    feedback_store.setup()
    watcher.setup()
    with get_store() as store:
        store.setup()
    with get_checkpointer() as saver:
        saver.setup()
