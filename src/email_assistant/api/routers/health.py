from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from email_assistant.memory.store import setup_database
from email_assistant.services.health import check_all

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    results = await run_in_threadpool(check_all)
    return {"ok": all(r["ok"] for r in results.values()), "services": results}


@router.post("/health/db-init")
async def db_init():
    await run_in_threadpool(setup_database)
    return {"ok": True}
