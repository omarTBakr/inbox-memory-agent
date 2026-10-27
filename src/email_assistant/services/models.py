"""List models per provider and probe whether a model works for this app."""

import time

import httpx
from langchain_core.tools import tool

from email_assistant.config_models import ModelConfig, options
from email_assistant.graph.common import Router
from email_assistant.llm import get_chat_model
from email_assistant.prompts import get_prompt
from email_assistant.settings import get_settings


def _get(url: str, headers: dict | None = None, params: dict | None = None) -> dict:
    r = httpx.get(url, headers=headers, params=params, timeout=get_settings().health_timeout_seconds * 3)
    r.raise_for_status()
    return r.json()


def list_models(provider: str, base_url: str, api_key: str, embeddings: bool = False) -> list[dict]:
    """[{name, capabilities}] from the provider's own model listing."""
    meta = options()["providers"][provider]
    base = (base_url or meta["base_url"]).rstrip("/")
    if provider == "ollama":
        models = []
        for m in _get(f"{base}/api/tags")["models"]:
            info = httpx.post(f"{base}/api/show", json={"model": m["name"]}, timeout=10).json()
            caps = info.get("capabilities", [])
            if embeddings == ("embedding" in caps):
                models.append({"name": m["name"], "capabilities": caps, "size": m.get("size")})
        return models
    if provider == "anthropic":
        data = _get(f"{base}{meta['models_path']}", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    params={"limit": 100})
        return [{"name": m["id"], "capabilities": ["tools"]} for m in data["data"]]
    if provider == "google_genai":
        data = _get(f"{base}{meta['models_path']}", params={"key": api_key, "pageSize": 1000})
        method = "embedContent" if embeddings else "generateContent"
        return [
            {"name": m["name"].removeprefix("models/"), "capabilities": m.get("supportedGenerationMethods", [])}
            for m in data["models"] if method in m.get("supportedGenerationMethods", [])
        ]
    data = _get(f"{base}{meta['models_path']}", headers={"Authorization": f"Bearer {api_key}"})
    names = sorted(m["id"] for m in data["data"])
    if provider == "openai":
        names = [n for n in names if ("embedding" in n) == embeddings]
    return [{"name": n, "capabilities": []} for n in names]


def probe(cfg: ModelConfig, api_key: str | None = None) -> dict:
    """Run the two things the app needs from a model: structured output and a tool call."""
    llm = get_chat_model(cfg, api_key=api_key)
    checks = {}

    start = time.monotonic()
    try:
        result = llm.with_structured_output(Router, method=cfg.resolved_structured_output()).invoke(
            get_prompt("probe/structured").compile())
        checks["structured_output"] = {"ok": True, "detail": f"classification={result.classification}"}
    except Exception as e:
        checks["structured_output"] = {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:300]}"}
    checks["structured_output"]["ms"] = round((time.monotonic() - start) * 1000)

    @tool
    def check_calendar_availability(day: str) -> str:
        """Check calendar availability for a given day."""
        return ""

    start = time.monotonic()
    try:
        reply = llm.bind_tools([check_calendar_availability]).invoke(get_prompt("probe/tool_call").compile())
        ok = bool(reply.tool_calls)
        detail = f"called {reply.tool_calls[0]['name']}({reply.tool_calls[0]['args']})" if ok else "answered without calling the tool"
        checks["tool_calling"] = {"ok": ok, "detail": detail}
    except Exception as e:
        checks["tool_calling"] = {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:300]}"}
    checks["tool_calling"]["ms"] = round((time.monotonic() - start) * 1000)

    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}
