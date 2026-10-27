"""Observability.

- Langfuse: per-LLM-call tracing (pass `callbacks()` into graph.invoke config).
- MLflow: one run per stage / worker execution, plus LangGraph autolog traces.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from email_assistant.settings import get_settings

log = logging.getLogger(__name__)


@lru_cache
def langfuse_client():
    """The process-wide Langfuse client, configured from settings (not only env vars)."""
    from langfuse import Langfuse

    s = get_settings()
    return Langfuse(public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key.get_secret_value(),
                    host=s.langfuse_host, environment=s.app_env)


def score(trace_id: str | None, name: str, value, data_type: str = "NUMERIC", comment: str | None = None) -> None:
    """Attach a score to a Langfuse trace; never fails the caller."""
    if not (trace_id and get_settings().langfuse_enabled):
        return
    try:
        langfuse_client().create_score(trace_id=trace_id, name=name, value=value, data_type=data_type, comment=comment)
    except Exception as e:
        log.warning("Langfuse score %s failed: %s", name, e)


def sync_model_prices() -> list[str]:
    """Create Langfuse model definitions from MODEL_PRICES_PATH when missing or when prices changed."""
    import yaml

    s = get_settings()
    wanted = yaml.safe_load(s.path(s.model_prices_path).read_text())["models"]
    api = langfuse_client().api
    existing, page = {}, 1
    while True:  # Langfuse lists its built-in models too, across several pages
        listing = api.models.list(page=page, limit=100)
        for model in sorted(listing.data, key=lambda m: m.start_date or datetime.min.replace(tzinfo=UTC)):
            if not model.is_langfuse_managed:
                existing[model.model_name] = model  # newest definition per name wins
        if page >= listing.meta.total_pages:
            break
        page += 1
    report = []
    for m in wanted:
        price_in, price_out = m["input_per_million"] / 1e6, m["output_per_million"] / 1e6
        current = existing.get(m["model_name"])
        if current and current.match_pattern == m["match_pattern"] and current.input_price == price_in \
                and current.output_price == price_out:
            report.append(f"{m['model_name']}: unchanged")
            continue
        # a new definition (start_date now) takes over from the old one for new generations
        api.models.create(model_name=m["model_name"], match_pattern=m["match_pattern"], unit="TOKENS",
                          input_price=price_in, output_price=price_out, start_date=datetime.now(UTC))
        report.append(f"{m['model_name']}: {'updated' if current else 'created'} "
                      f"(${m['input_per_million']}/${m['output_per_million']} per 1M tokens in/out)")
    return report


def new_trace_id() -> str | None:
    if not get_settings().langfuse_enabled:
        return None
    from langfuse import Langfuse

    return Langfuse.create_trace_id()


def callbacks(trace_id: str | None = None) -> list[Any]:
    """LangChain callbacks to attach to every graph run (`trace_id`: use this Langfuse trace id)."""
    s = get_settings()
    if not s.langfuse_enabled:
        return []
    from langfuse.langchain import CallbackHandler

    langfuse_client()  # the handler uses this configured client
    context = {"trace_id": trace_id} if trace_id else None
    return [CallbackHandler(public_key=s.langfuse_public_key, trace_context=context)]


def init_mlflow() -> None:
    import mlflow

    s = get_settings()
    mlflow.set_tracking_uri(s.mlflow_tracking_uri)
    mlflow.set_experiment(s.mlflow_experiment_name)
    mlflow.langchain.autolog()


@contextmanager
def stage_run(stage: str, **params: Any) -> Iterator[Any]:
    """MLflow run for one stage execution; resumes the run when launched by `mlflow run`."""
    s = get_settings()
    if not s.mlflow_enabled:
        yield None
        return
    import mlflow

    init_mlflow()
    with mlflow.start_run(run_name=stage) as run:
        mlflow.set_tags({"stage": stage, "environment": s.app_env})
        mlflow.log_params({
            "llm_model": s.llm_model,
            "embedding_model": s.embedding_model,
            "prompt_source": s.prompt_source,
            "prompt_label": s.prompt_label,
            **params,
        })
        yield run


def log_results(rows: list[dict[str, Any]], metrics: dict[str, float]) -> None:
    """Attach per-email results and summary metrics to the active MLflow run."""
    if not get_settings().mlflow_enabled:
        return
    import mlflow

    mlflow.log_metrics(metrics)
    mlflow.log_table({k: [r[k] for r in rows] for k in rows[0]}, artifact_file="results.json")


def flush() -> None:
    """Send buffered Langfuse events before the process exits."""
    if get_settings().langfuse_enabled:
        langfuse_client().flush()
