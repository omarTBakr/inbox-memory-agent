"""Is the infrastructure the assistant needs reachable?"""

import time

import httpx
import psycopg

from email_assistant import config_store
from email_assistant.settings import get_settings


def _timed(check) -> dict:
    start = time.monotonic()
    try:
        detail = check()
        ok = True
    except Exception as e:
        detail, ok = f"{type(e).__name__}: {e}", False
    return {"ok": ok, "detail": detail, "ms": round((time.monotonic() - start) * 1000)}


def _http(url: str) -> str:
    r = httpx.get(url, timeout=get_settings().health_timeout_seconds)
    r.raise_for_status()
    return f"HTTP {r.status_code}"


def _postgres() -> str:
    timeout = int(get_settings().health_timeout_seconds) or 1
    with psycopg.connect(get_settings().database_url.get_secret_value(), connect_timeout=timeout) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        vector = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        tables = conn.execute("SELECT to_regclass('app_config') IS NOT NULL AND to_regclass('store') IS NOT NULL").fetchone()[0]
    if not vector:
        raise RuntimeError(f"Postgres {version} without pgvector")
    if not tables:
        raise RuntimeError("tables missing: run 'Initialise database'")
    return f"Postgres {version}, pgvector {vector[0]}"


def check_all() -> dict[str, dict]:
    s = get_settings()
    results = {"postgres": _timed(_postgres)}
    if s.langfuse_enabled:
        results["langfuse"] = _timed(lambda: _http(f"{s.langfuse_host}/api/public/health"))
    if s.mlflow_enabled:
        results["mlflow"] = _timed(lambda: _http(f"{s.mlflow_tracking_uri}/health"))
    model, embeddings = config_store.section("model"), config_store.section("embeddings")
    ollama_urls = {c.resolved_base_url() for c in (model, embeddings) if c.provider == "ollama"}
    for url in ollama_urls:
        results["ollama"] = _timed(lambda url=url: _http(f"{url}/api/version"))
    return results
