import time

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from email_assistant import config_store
from email_assistant.config_models import EmbeddingsConfig, ModelConfig
from email_assistant.llm import get_embeddings
from email_assistant.services.models import probe

router = APIRouter(tags=["models"])


class ProbeRequest(BaseModel):
    # unsaved form values; api_key empty uses the saved one
    data: dict
    api_key: str = ""


@router.post("/models/probe")
async def probe_model(body: ProbeRequest):
    cfg = ModelConfig.model_validate(body.data)
    key = body.api_key or config_store.secret("model", "api_key")
    return await run_in_threadpool(probe, cfg, key)


@router.post("/models/probe-embeddings")
async def probe_embeddings(body: ProbeRequest):
    cfg = EmbeddingsConfig.model_validate(body.data)
    key = body.api_key or config_store.secret("embeddings", "api_key")

    def run():
        start = time.monotonic()
        try:
            vector = get_embeddings(cfg, api_key=key).embed_query("probe")
        except Exception as e:
            return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:300]}"}
        ms = round((time.monotonic() - start) * 1000)
        ok = len(vector) == cfg.dims
        detail = f"{len(vector)} dimensions" + ("" if ok else f", but dims is set to {cfg.dims}")
        return {"ok": ok, "detail": detail, "dims": len(vector), "ms": ms}

    return await run_in_threadpool(run)
