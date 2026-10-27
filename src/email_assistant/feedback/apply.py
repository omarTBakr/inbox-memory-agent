"""Turn a 👍/👎 on a handled email into memory updates.

- 👍                 the email + its label become an episodic example (handle similar ones the same way)
- 👎 + right label   the corrected label becomes an episodic example
- 👎 + comment       the comment rewrites the procedures it is about (procedural memory)
Every rating is also recorded as a Langfuse score on the email's trace and as an MLflow
metric on the run that handled it.
"""

import logging
from typing import get_args

from email_assistant.emails import Classification, Email
from email_assistant import tracing
from email_assistant.feedback import store
from email_assistant.memory import procedural
from email_assistant.memory.episodic import record_example
from email_assistant.memory.store import get_store
from email_assistant.profile import load_profile
from email_assistant.prompts import get_prompt
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)


def _summary(key: str, **values) -> str:
    return get_prompt("notifications/feedback_summaries").config[key].format(**values)


def _get(item_id: str) -> dict:
    item = store.get(item_id)
    if not item:
        raise ValueError(f"Unknown feedback item {item_id!r}")
    return item


def _score(item: dict, value: int, comment: str | None = None) -> None:
    s = get_settings()
    tracing.score(item.get("trace_id"), "user_feedback", value, comment=comment)
    tracing.flush()
    if s.mlflow_enabled and item.get("mlflow_run_id"):
        try:
            import mlflow

            counts = store.stats(item["mlflow_run_id"])
            client = mlflow.MlflowClient(s.mlflow_tracking_uri)
            client.log_metric(item["mlflow_run_id"], "feedback_up", counts["up"])
            client.log_metric(item["mlflow_run_id"], "feedback_down", counts["down"])
        except Exception as e:
            log.warning("MLflow feedback metric failed: %s", e)


def _record(item: dict, label: str, source: str) -> dict:
    email = Email(**item["email"])
    with get_store() as memory:
        key = record_example(memory, load_profile().user.id, email, label, source=source)
    return {"memory": "episodic", "label": label, "key": key}


def thumbs_up(item_id: str) -> str:
    item = _get(item_id)
    change = _record(item, item["classification"], "feedback:up")
    store.update(item_id, rating="up", applied=[*item["applied"], change])
    _score(item, 1)
    return _summary("up")


def thumbs_down(item_id: str) -> str:
    """👎 without detail yet: the user is asked what was wrong next."""
    item = _get(item_id)
    store.update(item_id, rating="down")
    _score(item, 0)
    return _summary("down")


def correct_label(item_id: str, label: str) -> str:
    """Choosing the label the assistant gave (again) is a 👍; any other label is a correction."""
    if label not in get_args(Classification):
        raise ValueError(f"Unknown label {label!r}")
    item = _get(item_id)
    if label == item["classification"]:
        store.update(item_id, corrected_label=None)
        return thumbs_up(item_id)
    change = _record(item, label, "feedback:label")
    store.update(item_id, rating="down", corrected_label=label, applied=[*item["applied"], change])
    _score(item, 0, comment=f"should be {label}")
    return _summary("label", label=label)


def reply_feedback(item_id: str, comment: str) -> str:
    """Free-text feedback on what the assistant did: rewrites the procedures it is about."""
    item = _get(item_id)
    profile = load_profile()
    with get_store() as memory:
        changes = procedural.optimize(memory, profile.user.id, profile, item["trajectory"], comment)
    applied = [{"memory": "procedural", "name": c["name"], "version": c["version"]} for c in changes]
    store.update(item_id, rating="down", comment=comment, applied=[*item["applied"], *applied])
    _score(item, 0, comment=comment)
    if not changes:
        return _summary("procedural_none")
    return _summary("procedural", names=", ".join(c["name"] for c in changes))


def not_spam(item_id: str) -> str:
    """Move a Spam email to the Inbox. Rescuing it also says it mattered: an ignored one is
    corrected to 'notify', a notified one gets a 👍, so similar emails are surfaced next time."""
    from email_assistant.gmail import actions

    item = _get(item_id)
    if item["email"].get("folder") != "spam":
        raise ValueError("This email was not in Spam")
    if not item["moved_to_inbox"]:
        actions.not_spam(item["email_ref"])
        store.update(item_id, moved_to_inbox=True)
    moved = get_prompt("notifications/moved_to_inbox").compile(subject=item["email"]["subject"])
    if item["classification"] == "ignore":
        return f"{moved}. {correct_label(item_id, 'notify')}"
    return f"{moved}. {thumbs_up(item_id)}"


def saved_message(summary: str) -> str:
    return get_prompt("notifications/feedback_saved").compile(summary=summary)
