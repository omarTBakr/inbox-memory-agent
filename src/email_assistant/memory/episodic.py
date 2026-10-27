"""Episodic memory: past emails with the triage label they should get.

Examples are recorded from user feedback (CLI now, UI later) and the most similar
ones are shown to the triage step as few-shot examples.
"""

import hashlib
import json
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_store
from langgraph.store.base import BaseStore, SearchItem

from email_assistant.emails import Classification, Email
from email_assistant.memory.store import USER_ID_KEY, namespace
from email_assistant.prompts import get_prompt
from email_assistant.settings import get_settings


def episodic_namespace(user_id: str) -> tuple[str, ...]:
    return namespace(user_id, get_settings().memory_episodic_collection)


def _key(email: Email) -> str:
    """Same email -> same key, so new feedback replaces the old label."""
    raw = json.dumps([email["author"], email["subject"], email["email_thread"]])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _query(email: Email) -> str:
    return f"{email['author']}\n{email['subject']}\n{email['email_thread']}"


def record_example(store: BaseStore, user_id: str, email: Email, label: Classification, source: str) -> str:
    key = _key(email)
    value = {"email": dict(email), "label": label, "source": source, "recorded_at": datetime.now(UTC).isoformat()}
    # embed only the email so similarity is about content, not the label
    store.put(episodic_namespace(user_id), key, value, index=["email"])
    return key


def find_examples(store: BaseStore, user_id: str, email: Email) -> list[SearchItem]:
    s = get_settings()
    items = store.search(episodic_namespace(user_id), query=_query(email), limit=s.episodic_top_k)
    return [i for i in items if i.score is None or i.score >= s.episodic_min_score]


def format_example(value: dict) -> str:
    email = value["email"]
    return get_prompt("memory/episodic_few_shot").compile(
        subject=email["subject"],
        from_email=email["author"],
        to_email=email["to"],
        content=email["email_thread"],
        result=value["label"],
    )


def triage_examples(email: Email, config: RunnableConfig) -> list[str]:
    """Few-shot examples for the triage router (runs inside the graph)."""
    user_id = config["configurable"][USER_ID_KEY]
    return [format_example(item.value) for item in find_examples(get_store(), user_id, email)]
