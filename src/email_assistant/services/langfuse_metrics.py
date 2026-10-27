"""Headline numbers for the Visualizations tab, from the Langfuse metrics API (v2, real-time)."""

import json
import time
from datetime import UTC, datetime, timedelta

from email_assistant.settings import get_settings
from email_assistant.tracing import langfuse_client


def _filter(column: str, value, kind: str = "string", operator: str = "=") -> dict:
    return {"column": column, "operator": operator, "value": value, "type": kind}


# KPI -> (view, metric, filters, group by). Result keys are "<aggregation>_<measure>".
KPIS: dict[str, dict] = {
    "feedback": {"view": "scores-numeric", "metrics": [("value", "avg"), ("count", "count")],
                 "filters": [_filter("name", "user_feedback")]},
    "triage_mix": {"view": "scores-categorical", "metrics": [("count", "count")],
                   "filters": [_filter("name", "triage_classification")], "dimension": "stringValue"},
    "cost": {"view": "observations", "metrics": [("totalCost", "sum")], "filters": []},
    "latency_p95": {"view": "observations", "metrics": [("latency", "p95")],
                    "filters": [_filter("isRootObservation", True, "boolean")]},
    "tokens": {"view": "observations", "metrics": [("totalTokens", "sum")],
               "filters": [_filter("type", "GENERATION")]},
    "warnings": {"view": "scores-numeric", "metrics": [("value", "sum")],
                 "filters": [_filter("name", "notification_warnings")]},
}


def build_query(kpi: str, start: datetime, end: datetime, environment: str | None, daily: bool) -> dict:
    spec = KPIS[kpi]
    filters = list(spec["filters"])
    if environment:
        filters.append(_filter("environment", [environment], "stringOptions", "any of"))
    query = {
        "view": spec["view"],
        "metrics": [{"measure": m, "aggregation": a} for m, a in spec["metrics"]],
        "dimensions": [{"field": spec["dimension"]}] if spec.get("dimension") else [],
        "filters": filters,
        "fromTimestamp": start.isoformat(),
        "toTimestamp": end.isoformat(),
    }
    if daily:
        query["timeDimension"] = {"granularity": "day"}
    return query


def _run(query: dict) -> list[dict]:
    return langfuse_client().api.metrics.metrics(query=json.dumps(query)).data


def shape(kpi: str, total: list[dict], series: list[dict]) -> dict:
    """Turn raw metric rows into {value, ..., series} for one KPI; value None when there is no data."""
    if kpi == "triage_mix":
        return {"value": {row["stringValue"]: row["count_count"] for row in total} or None}
    key = "{1}_{0}".format(*KPIS[kpi]["metrics"][0])
    value = total[0].get(key) if total else None
    shaped = {"value": value, "series": [{"day": r["time_dimension"], "value": r.get(key)} for r in series]}
    if kpi == "feedback":
        shaped["count"] = total[0].get("count_count", 0) if total else 0
    return shaped


_cache: dict[tuple, tuple[float, dict]] = {}


def kpis(days: int, environment: str | None) -> dict:
    key = (days, environment)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < get_settings().visualizations_cache_seconds:
        return hit[1]
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    result = {}
    for kpi in KPIS:
        try:
            total = _run(build_query(kpi, start, end, environment, daily=False))
            series = [] if kpi == "triage_mix" else _run(build_query(kpi, start, end, environment, daily=True))
            result[kpi] = shape(kpi, total, series)
        except Exception as e:  # one failing query must not blank the whole strip
            result[kpi] = {"value": None, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    payload = {"days": days, "environment": environment, "kpis": result}
    _cache[key] = (time.monotonic(), payload)
    return payload
