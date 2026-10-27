from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from email_assistant.api.main import app
from email_assistant.services.langfuse_metrics import KPIS, build_query, shape

END = datetime(2026, 10, 27, tzinfo=UTC)
START = END - timedelta(days=7)


def test_query_filters_by_score_name_environment_and_period():
    q = build_query("feedback", START, END, "development", daily=True)
    assert q["view"] == "scores-numeric" and q["timeDimension"] == {"granularity": "day"}
    assert {"column": "name", "operator": "=", "value": "user_feedback", "type": "string"} in q["filters"]
    assert {"column": "environment", "operator": "any of", "value": ["development"], "type": "stringOptions"} in q["filters"]
    assert q["fromTimestamp"].startswith("2026-10-20")
    assert all(f["column"] != "environment" for f in build_query("cost", START, END, None, False)["filters"])


def test_shape_handles_data_and_empty_results():
    fb = shape("feedback", [{"avg_value": 0.75, "count_count": 4}], [{"time_dimension": "2026-10-26", "avg_value": 1}])
    assert fb == {"value": 0.75, "count": 4, "series": [{"day": "2026-10-26", "value": 1}]}
    assert shape("cost", [], []) == {"value": None, "series": []}
    mix = shape("triage_mix", [{"stringValue": "ignore", "count_count": 3}], [])
    assert mix == {"value": {"ignore": 3}}
    assert shape("triage_mix", [], []) == {"value": None}
    assert set(KPIS) == {"feedback", "triage_mix", "cost", "latency_p95", "tokens", "warnings"}


def test_config_lists_langfuse_pages():
    body = TestClient(app).get("/api/visualizations/config").json()
    assert body["embed_url"].endswith(":3002")
    assert body["pages"]["traces"].startswith("/project/") and "{project}" not in body["pages"]["traces"]
