"""Ignored-email digest: one Telegram message listing ignored emails, 👍/👎 per email."""

from email_assistant import config_store
from email_assistant.feedback import store
from email_assistant.notifications import telegram_bot
from email_assistant.notifications.schemas import EmailRef, IgnoredDigest
from email_assistant.notifications.summary import digest_item, render
from email_assistant.settings import get_settings


def send_digest() -> dict:
    """Send pending ignored emails (in chunks); returns what was sent or would be sent."""
    cfg = config_store.section("notifications")
    pending = store.pending_digest()
    if not pending:
        return {"sent": 0, "messages": []}
    size = get_settings().digest_max_items
    messages = []
    for start in range(0, len(pending), size):
        chunk = pending[start:start + size]
        digest = IgnoredDigest(items=[
            digest_item(row["id"], EmailRef(ref=row["email_ref"], sender=row["email"]["author"],
                                            to=row["email"]["to"], subject=row["email"]["subject"],
                                            folder=row["email"].get("folder", "inbox")), row["reasoning"])
            for row in chunk
        ])
        text = render(digest)
        if cfg.dry_run or "telegram" not in cfg.channels:
            messages.append({"text": text, "sent": False})
            continue
        message_id = telegram_bot.send(text, cfg.telegram_chat_id, keyboard=telegram_bot.digest_keyboard(chunk))
        for row in chunk:
            store.update(row["id"], digest_sent=True, telegram_message_id=message_id)
        messages.append({"text": text, "sent": True, "message_id": message_id})
    return {"items": len(pending), "messages_sent": sum(m["sent"] for m in messages), "messages": messages}
