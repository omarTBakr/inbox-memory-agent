"""Telegram Bot API: messages with 👍/👎 buttons, and the listener that receives the clicks.

Callback data is "fb:<feedback id>:<action>" with action one of
  up | down | label_<ignore|notify|respond> | why | not_spam
Only updates from the configured chat are acted on. Free-text feedback arrives as a reply
to the bot's "what should change?" message (matched by its message id).
"""

import logging
import threading
from datetime import date, datetime
from typing import get_args
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from email_assistant import config_store
from email_assistant.config_models import options
from email_assistant.emails import Classification
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)


def api(method: str, timeout: float | None = None, **payload) -> dict:
    s = get_settings()
    url = f"{s.telegram_api_base}/bot{config_store.secret('notifications', 'telegram_bot_token')}/{method}"
    r = httpx.post(url, json=payload, timeout=timeout or s.notify_timeout_seconds)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', r.status_code)}")
    return data["result"]


def _button(label: str, item_id: str, action: str) -> dict:
    return {"text": label, "callback_data": f"fb:{item_id}:{action}"}


def _current(item: dict) -> str:
    return item.get("corrected_label") or item["classification"]


def _labels(item: dict, prefix: str = "") -> list[dict]:
    b = options()["telegram_buttons"]
    current = _current(item)
    return [
        _button(f"{prefix}{b['selected'] if c == current else ''}{b[f'label_{c}']}", item["id"], f"label_{c}")
        for c in get_args(Classification)
    ]


def _spam_row(item: dict, prefix: str = "") -> list[list[dict]]:
    """'Not spam' for an email found in Spam; becomes a plain mark once it was moved."""
    if (item.get("email") or {}).get("folder") != "spam":
        return []
    b = options()["telegram_buttons"]
    label = b["not_spam_done"] if item.get("moved_to_inbox") else b["not_spam"]
    return [[_button(f"{prefix}{label}", item["id"], "not_spam")]]


def feedback_keyboard(item: dict) -> list[list[dict]]:
    """Labels (current one ticked) and 👍 / 👎 / ✍️ for one notification; `item` is its feedback row."""
    b = options()["telegram_buttons"]
    rated = {r: b["given"] if item.get("rating") == r else "" for r in ("up", "down")}
    return [
        _labels(item),
        [_button(b["up"] + rated["up"], item["id"], "up"), _button(b["down"] + rated["down"], item["id"], "down"),
         _button(b["why"], item["id"], "why")],
        *_spam_row(item),
    ]


def digest_keyboard(items: list[dict]) -> list[list[dict]]:
    """One row per digest email: its number with the three labels, and ✍️ (plus 'Not spam' for Spam)."""
    b = options()["telegram_buttons"]
    rows = []
    for n, item in enumerate(items, start=1):
        rows.append([*_labels(item, prefix=f"{n} "), _button(f"{n} {b['why_short']}", item["id"], "why")])
        rows.extend(_spam_row(item, prefix=f"{n} "))
    return rows


def send(text: str, chat_id: str, keyboard: list[list[dict]] | None = None, reply_to: int | None = None,
         force_reply: bool = False) -> int:
    payload = {"chat_id": chat_id, "text": text[: get_settings().notify_max_chars]}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    if force_reply:
        payload["reply_markup"] = {"force_reply": True}
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    return api("sendMessage", **payload)["message_id"]


class Listener:
    """Long-polls getUpdates in a background thread; one per bot token."""

    def __init__(self):
        self.seen_chats: dict[int, dict] = {}
        self.running = False
        self.last_error: str | None = None
        self._offset: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._digest_day: date | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="telegram-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if not config_store.secret("notifications", "telegram_bot_token"):
                self.running = False
                self._stop.wait(5)
                continue
            try:
                self.running = True
                updates = self._poll()
                for update in updates:
                    self._offset = update["update_id"] + 1
                    self._handle(update)
                self._maybe_digest()
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                log.warning("Telegram listener: %s", e)
                self._stop.wait(5)

    def _poll(self) -> list[dict]:
        s = get_settings()
        url = (f"{s.telegram_api_base}/bot{config_store.secret('notifications', 'telegram_bot_token')}/getUpdates")
        payload = {"timeout": s.telegram_poll_timeout, "allowed_updates": ["message", "callback_query"]}
        if self._offset is not None:
            payload["offset"] = self._offset
        data = httpx.post(url, json=payload, timeout=s.telegram_poll_timeout + 10).json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description"))
        return data["result"]

    def _handle(self, update: dict) -> None:
        message = update.get("message") or (update.get("callback_query") or {}).get("message") or {}
        chat = message.get("chat") or {}
        if chat:
            self.seen_chats[chat["id"]] = {"chat_id": chat["id"], "name": chat.get("username") or chat.get("first_name")}
        if str(chat.get("id")) != config_store.section("notifications").telegram_chat_id:
            return  # only the owner's chat may change memory
        if "callback_query" in update:
            self._callback(update["callback_query"])
        elif (message.get("reply_to_message") or {}).get("message_id") and message.get("text"):
            self._comment(message)

    def _callback(self, query: dict) -> None:
        from email_assistant.feedback import apply, store
        from email_assistant.prompts import get_prompt

        chat_id = str(query["message"]["chat"]["id"])
        try:
            _, item_id, action = query.get("data", "").split(":", 2)
        except ValueError:
            return
        item = store.get(item_id)
        if not item:
            api("answerCallbackQuery", callback_query_id=query["id"], text="Unknown email")
            return
        subject = item["email"]["subject"]
        origin = query["message"]["message_id"]
        if action == "up":
            toast = apply.thumbs_up(item_id)
        elif action == "down":
            toast = apply.thumbs_down(item_id)
        elif action.startswith("label_"):
            toast = apply.correct_label(item_id, action.removeprefix("label_"))
        elif action == "why":
            prompt_id = send(get_prompt("notifications/feedback_why").compile(subject=subject), chat_id, force_reply=True)
            store.update(item_id, prompt_message_id=prompt_id)
            toast = None
        elif action == "not_spam":
            try:
                toast = apply.not_spam(item_id)
            except Exception as e:
                toast = f"Could not move it: {e}"
        else:
            return
        api("answerCallbackQuery", callback_query_id=query["id"], text=(toast or "")[:200])
        self._refresh_keyboard(chat_id, origin)

    def _refresh_keyboard(self, chat_id: str, message_id: int) -> None:
        """Redraw the buttons so the tick follows the latest feedback."""
        from email_assistant.feedback import store

        items = store.by_message(message_id)
        if not items:
            return
        keyboard = digest_keyboard(items) if items[0]["digest_sent"] else feedback_keyboard(items[0])
        try:
            api("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": keyboard})
        except RuntimeError as e:  # "message is not modified" when nothing changed
            log.debug("keyboard unchanged: %s", e)

    def _comment(self, message: dict) -> None:
        from email_assistant.feedback import apply, store

        item = store.by_prompt_message(message["reply_to_message"]["message_id"])
        if not item:
            return
        chat_id = str(message["chat"]["id"])
        api("sendChatAction", chat_id=chat_id, action="typing")
        send(apply.saved_message(apply.reply_feedback(item["id"], message["text"])), chat_id,
             reply_to=message["message_id"])

    def _maybe_digest(self) -> None:
        from email_assistant.feedback.digest import send_digest

        cfg = config_store.section("notifications")
        if not (cfg.ignored_digest and "telegram" in cfg.channels):
            return
        try:
            tz = ZoneInfo(config_store.section("profile").user.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        if self._digest_day != now.date() and now.strftime("%H:%M") >= cfg.digest_time:
            self._digest_day = now.date()
            send_digest()


listener = Listener()
