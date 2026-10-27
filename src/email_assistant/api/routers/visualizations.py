"""Visualizations tab: where the embedded Langfuse lives, and headline numbers from it."""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from email_assistant.config_models import options
from email_assistant.services.langfuse_metrics import kpis
from email_assistant.settings import get_settings

router = APIRouter(tags=["visualizations"])


@router.get("/visualizations/config")
async def config():
    s = get_settings()
    pages = {name: path.format(project=s.langfuse_init_project_id) for name, path in options()["langfuse_pages"].items()}
    return {
        "enabled": s.langfuse_enabled,
        "embed_url": s.langfuse_embed_url,
        "direct_url": s.langfuse_host,
        "environment": s.app_env,
        "periods": options()["visualization_periods"],
        "pages": pages,
    }


@router.get("/visualizations/kpis")
async def get_kpis(days: int = 7, environment: str = "current"):
    """environment: "current" (APP_ENV), "all", or an environment name."""
    if days not in options()["visualization_periods"]:
        raise HTTPException(400, f"days must be one of {options()['visualization_periods']}")
    env = {"current": get_settings().app_env, "all": None}.get(environment, environment)
    return await run_in_threadpool(kpis, days, env)
