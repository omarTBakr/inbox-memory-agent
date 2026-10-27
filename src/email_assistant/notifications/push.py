"""Send a text to the user's notification channels; dry-run prints instead.

- telegram: Bot API sendMessage to the configured telegram_chat_id.
- telegram_self: your own account posts into Saved Messages (see telegram_self.py).
"""

import logging

import httpx

from email_assistant import config_store
from email_assistant.config_models import Notifications
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)


def _telegram(text: str, cfg: Notifications, keyboard: list | None = None) -> int:
    from email_assistant.notifications import telegram_bot

    return telegram_bot.send(text, cfg.telegram_chat_id, keyboard=keyboard)


def _telegram_self(text: str, cfg: Notifications, keyboard: list | None = None) -> int:
    # your own account can't receive button clicks, so Saved Messages get no buttons
    from email_assistant.notifications import telegram_self

    return telegram_self.send(text)


SENDERS = {"telegram": _telegram, "telegram_self": _telegram_self}


def push(text: str, cfg: Notifications, channels: list[str] | None = None, dry_run: bool | None = None,
         keyboard: list | None = None) -> list[dict]:
    """Send `text` to the configured (or given) channels; one result per channel, never raises.

    `keyboard`: Telegram inline buttons (feedback) for the bot channel.
    """
    text = text[: get_settings().notify_max_chars]
    dry_run = cfg.dry_run if dry_run is None else dry_run
    results = []
    for channel in channels or cfg.channels:
        if dry_run:
            results.append({"channel": channel, "ok": True, "detail": "dry-run"})
            continue
        try:
            message_id = SENDERS[channel](text, cfg, keyboard)
            results.append({"channel": channel, "ok": True, "detail": f"message_id={message_id}", "message_id": message_id})
        except Exception as e:  # a failed push must not fail the email run
            log.warning("Notification via %s failed: %s", channel, e)
            results.append({"channel": channel, "ok": False, "detail": str(e)})
    return results


def telegram_chat_ids(token: str | None = None) -> list[dict]:
    """Chats that recently messaged the bot (send /start to it first)."""
    from email_assistant.notifications.telegram_bot import listener

    if listener.running:  # it already consumed the updates; it remembers the chats it saw
        return list(listener.seen_chats.values())
    s = get_settings()
    url = f"{s.telegram_api_base}/bot{token or config_store.secret('notifications', 'telegram_bot_token')}/getUpdates"
    r = httpx.get(url, timeout=s.notify_timeout_seconds)
    r.raise_for_status()
    chats = {}
    for update in r.json()["result"]:
        chat = (update.get("message") or update.get("my_chat_member") or {}).get("chat")
        if chat:
            chats[chat["id"]] = {"chat_id": chat["id"], "name": chat.get("username") or chat.get("title") or chat.get("first_name")}
    return list(chats.values())
