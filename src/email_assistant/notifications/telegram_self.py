"""telegram_self channel: post into your own Saved Messages from your Telegram account.

Uses Telegram's user API (Telethon). Login: send_code() -> the code arrives in your
Telegram app -> verify(code[, 2FA password]). The session is stored encrypted as the
notifications secret `telegram_session`; it grants access to your account.
"""

import asyncio

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from email_assistant import config_store

# login in progress: session string + phone_code_hash between the two requests
_pending: dict[str, str] = {}


def _client(session: str = "") -> TelegramClient:
    cfg = config_store.section("notifications")
    api_hash = config_store.secret("notifications", "telegram_api_hash")
    if not (cfg.telegram_api_id and api_hash and cfg.telegram_phone):
        raise ValueError("Save the Telegram api_id, api_hash and phone first")
    return TelegramClient(StringSession(session), int(cfg.telegram_api_id), api_hash)


def _run(coro):
    return asyncio.run(coro)


def send_code() -> None:
    async def go():
        client = _client()
        await client.connect()
        try:
            sent = await client.send_code_request(config_store.section("notifications").telegram_phone)
            _pending.update(session=client.session.save(), phone_code_hash=sent.phone_code_hash)
        finally:
            await client.disconnect()

    _run(go())


def verify(code: str, password: str = "") -> dict:
    if not _pending:
        raise ValueError("Request a login code first")

    async def go():
        client = _client(_pending["session"])
        await client.connect()
        try:
            try:
                await client.sign_in(config_store.section("notifications").telegram_phone, code,
                                     phone_code_hash=_pending["phone_code_hash"])
            except SessionPasswordNeededError:
                if not password:
                    _pending["session"] = client.session.save()
                    return {"connected": False, "needs_password": True}
                await client.sign_in(password=password)
            me = await client.get_me()
            config_store.set_secret("notifications", "telegram_session", client.session.save())
            _pending.clear()
            return {"connected": True, "name": me.first_name, "username": me.username}
        finally:
            await client.disconnect()

    return _run(go())


def status() -> dict:
    session = config_store.secret("notifications", "telegram_session")
    if not session:
        return {"connected": False}

    async def go():
        client = _client(session)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return {"connected": False, "detail": "session expired; log in again"}
            me = await client.get_me()
            return {"connected": True, "name": me.first_name, "username": me.username}
        finally:
            await client.disconnect()

    return _run(go())


def logout() -> None:
    config_store.delete_secret("notifications", "telegram_session")
    _pending.clear()


def send(text: str) -> int:
    session = config_store.secret("notifications", "telegram_session")
    if not session:
        raise RuntimeError("Telegram account not connected")

    async def go():
        client = _client(session)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram session expired; log in again")
            message = await client.send_message("me", text)
            return message.id
        finally:
            await client.disconnect()

    return _run(go())
