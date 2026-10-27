"""Feedback on handled emails: list, rate from the UI, send the ignored digest, listener status."""

from typing import get_args

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from email_assistant.emails import Classification
from email_assistant.feedback import apply, store
from email_assistant.feedback.digest import send_digest
from email_assistant.notifications.telegram_bot import listener

router = APIRouter(tags=["feedback"])


@router.get("/feedback")
async def list_feedback(limit: int = 50, offset: int = 0):
    return await run_in_threadpool(store.recent, limit, offset)


class Rating(BaseModel):
    rating: str
    label: str | None = None
    comment: str | None = None


@router.post("/feedback/{item_id}")
async def rate(item_id: str, body: Rating):
    """up | down | label (with label) | comment (with comment) | not_spam: same effect as the Telegram buttons."""
    if body.rating == "up":
        fn, args = apply.thumbs_up, (item_id,)
    elif body.rating == "down":
        fn, args = apply.thumbs_down, (item_id,)
    elif body.rating == "label" and body.label in get_args(Classification):
        fn, args = apply.correct_label, (item_id, body.label)
    elif body.rating == "comment" and body.comment:
        fn, args = apply.reply_feedback, (item_id, body.comment)
    elif body.rating == "not_spam":
        fn, args = apply.not_spam, (item_id,)
    else:
        raise HTTPException(400, "rating must be up, down, label (+label), comment (+comment) or not_spam")
    return {"summary": await run_in_threadpool(fn, *args), "item": await run_in_threadpool(store.get, item_id)}


@router.post("/feedback/digest/send")
async def digest_now():
    return await run_in_threadpool(send_digest)


@router.get("/feedback/listener")
async def listener_status():
    return {"running": listener.running, "last_error": listener.last_error}
