import psycopg
import pytest
from fastapi.testclient import TestClient

from email_assistant import config_store
from email_assistant.api.main import app
from email_assistant.settings import get_settings

TEST_USER = "pytest"


@pytest.fixture
def client():
    """API client whose config rows belong to a throwaway user, removed afterwards."""
    s = get_settings()
    real_user = s.app_user_id
    s.app_user_id = TEST_USER
    config_store.invalidate()
    try:
        yield TestClient(app)
    finally:
        with psycopg.connect(s.database_url.get_secret_value(), autocommit=True) as conn:
            for table in ("app_config", "app_config_history", "app_secrets"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (TEST_USER,))
        s.app_user_id = real_user
        config_store.invalidate()


def test_schema_marks_required_and_optional_fields(client):
    schema = client.get("/api/schema/profile").json()["schema"]
    user = schema["$defs"]["User"]
    assert {"name", "full_name", "email", "timezone"} <= set(user["required"])
    assert "role" not in user["required"]
    assert user["properties"]["timezone"]["ui"] == {"options": "timezones", "custom": False}
    assert user["properties"]["languages"]["ui"]["custom"] is True


def test_schema_lists_fixed_choices_and_secrets(client):
    body = client.get("/api/schema/notifications").json()
    channels = body["schema"]["properties"]["channels"]
    assert set(channels["items"]["enum"]) == {"telegram", "telegram_self"}
    # the Telegram session is set by the login flow, so it gets no input field
    assert {s["name"] for s in body["secrets"]} == {"telegram_bot_token", "telegram_api_hash"}


def test_unsaved_section_falls_back_to_yaml(client):
    body = client.get("/api/config/profile").json()
    assert body["source"] == "default"
    assert body["data"]["user"]["id"]


def test_save_roundtrip_versions_and_masks_secrets(client):
    data = client.get("/api/config/gmail").json()["data"]
    data["approval_mode"] = "approve"
    first = client.put("/api/config/gmail", json={"data": data}).json()
    second = client.put("/api/config/model", json={"data": client.get("/api/config/model").json()["data"],
                                                     "secrets": {"api_key": "sk-test-123"}}).json()
    assert first["version"] == 1
    assert second["secrets"] == {"api_key": True}
    body = client.get("/api/config/gmail").json()
    assert body["source"] == "saved" and body["data"]["approval_mode"] == "approve"
    assert "sk-test-123" not in client.get("/api/config/model").text
    assert config_store.secret("model", "api_key") == "sk-test-123"


def test_invalid_section_is_rejected_with_field_errors(client):
    data = client.get("/api/config/notifications").json()["data"]
    data["channels"] = ["telegram"]
    data["telegram_chat_id"] = ""
    r = client.put("/api/config/notifications", json={"data": data})
    assert r.status_code == 422
    assert "telegram_chat_id" in str(r.json()["detail"])


def test_options_come_from_config(client):
    assert {"value": "Africa/Cairo", "label": "Africa/Cairo"} in client.get("/api/options/timezones").json()
    providers = {p["value"] for p in client.get("/api/options/providers").json()}
    assert {"ollama", "anthropic", "openai", "openai_compatible", "google_genai"} == providers
    assert "anthropic" not in {p["value"] for p in client.get("/api/options/embedding_providers").json()}


def test_setup_status_lists_steps(client):
    body = client.get("/api/setup/status").json()
    assert body["order"][0] == "health" and body["order"][-1] == "review"
    assert body["steps"]["profile"]["saved"] is False
