from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from email_assistant import config_store
from email_assistant.notifications import telegram_self
from email_assistant.notifications.push import push, telegram_chat_ids
from email_assistant.prompts import get_prompt

router = APIRouter(tags=["notifications"])


class TestRequest(BaseModel):
    channel: str


@router.post("/notifications/test")
async def test(body: TestRequest):
    """Really send the test message on one channel (ignores dry-run), using the saved settings."""

    def send():
        cfg = config_store.section("notifications")
        name = config_store.section("profile").user.name
        return push(get_prompt("notifications/test").compile(name=name), cfg, channels=[body.channel], dry_run=False)[0]

    return await run_in_threadpool(send)


@router.get("/notifications/telegram/chats")
async def telegram_chats():
    if not config_store.secret("notifications", "telegram_bot_token"):
        raise HTTPException(400, "Save the Telegram bot token first")
    try:
        return await run_in_threadpool(telegram_chat_ids)
    except Exception as e:
        raise HTTPException(502, f"Telegram: {e}")


# ---------- telegram_self: your own account, Saved Messages ----------

class TelegramCode(BaseModel):
    code: str
    password: str = ""


def _call(fn, *args):
    try:
        return fn(*args)
    except ValueError:
        raise
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@router.get("/notifications/telegram-self/status")
async def telegram_self_status():
    return await run_in_threadpool(_call, telegram_self.status)


@router.post("/notifications/telegram-self/send-code")
async def telegram_self_send_code():
    await run_in_threadpool(_call, telegram_self.send_code)
    return {"ok": True}


@router.post("/notifications/telegram-self/verify")
async def telegram_self_verify(body: TelegramCode):
    return await run_in_threadpool(_call, telegram_self.verify, body.code.strip(), body.password)


@router.post("/notifications/telegram-self/logout")
async def telegram_self_logout():
    await run_in_threadpool(telegram_self.logout)
    return {"connected": False}
