"""Which setup steps are complete."""

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from email_assistant import config_store
from email_assistant.config_models import SECTIONS
from email_assistant.profile import _find_todos
from email_assistant.services.health import check_all

router = APIRouter(tags=["setup"])

# wizard order; each step is backed by a config section, except health and review
STEPS = ["health", "profile", "notifications", "gmail", "calendar", "model", "embeddings", "review"]


def _section_status(name: str) -> dict:
    data, source = config_store.raw_section(name)
    try:
        SECTIONS[name].model_validate(data)
        valid = True
    except Exception:
        valid = False
    todos = _find_todos(data)
    return {"saved": source == "saved", "valid": valid, "todo": todos, "done": source == "saved" and valid and not todos}


@router.get("/setup/status")
async def status():
    def compute():
        steps = {"health": {"done": all(r["ok"] for r in check_all().values())}}
        for name in SECTIONS:
            steps[name] = _section_status(name)
        steps["gmail"]["connected"] = config_store.secret_status("gmail")["token"]
        steps["gmail"]["done"] = steps["gmail"]["done"] and steps["gmail"]["connected"]
        steps["review"] = {"done": all(steps[s]["done"] for s in STEPS if s != "review")}
        return {"order": STEPS, "steps": steps}

    return await run_in_threadpool(compute)
