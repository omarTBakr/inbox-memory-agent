import zoneinfo

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from email_assistant import config_store
from email_assistant.config_models import options
from email_assistant.services.models import list_models

router = APIRouter(tags=["options"])


def _as_options(values: list) -> list[dict]:
    return [v if isinstance(v, dict) else {"value": v, "label": str(v)} for v in values]


@router.get("/options/{name}")
async def get_options(name: str):
    opts = options()
    if name == "timezones":
        return _as_options(sorted(zoneinfo.available_timezones()))
    if name in ("providers", "embedding_providers"):
        return [
            {"value": key, "label": p["label"], "kind": p["kind"], "api_key": p["api_key"], "base_url": p["base_url"]}
            for key, p in opts["providers"].items()
            if name == "providers" or p.get("embeddings")
        ]
    if name in opts and isinstance(opts[name], list):
        return _as_options(opts[name])
    raise HTTPException(404, f"Unknown option list {name!r}")


class ModelListRequest(BaseModel):
    provider: str
    base_url: str = ""
    # unsaved key typed in the form; empty uses the saved one
    api_key: str = ""
    embeddings: bool = False


@router.post("/options/models")
async def models(body: ModelListRequest):
    section = "embeddings" if body.embeddings else "model"
    key = body.api_key or config_store.secret(section, "api_key")
    try:
        found = await run_in_threadpool(list_models, body.provider, body.base_url, key, body.embeddings)
    except Exception as e:
        raise HTTPException(502, f"Could not list models: {e}")
    return [{"value": m["name"], "label": m["name"], "capabilities": m["capabilities"]} for m in found]
