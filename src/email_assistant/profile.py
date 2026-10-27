"""User profile: who the assistant works for.

Saved from the UI (Postgres sections `profile` + `notifications`); until then read from
config/user_profile.yml. The models live in config_models.
"""

import logging
from pathlib import Path

import yaml

from email_assistant import config_store
from email_assistant.config_models import (  # noqa: F401  (re-exported)
    Contact,
    Contacts,
    Notifications,
    Profile,
    Scheduling,
    TriageRules,
    User,
    WorkingHours,
    WritingStyle,
)
from email_assistant.settings import get_settings

log = logging.getLogger(__name__)


def _find_todos(value, path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _find_todos(v, f"{path}.{k}" if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _find_todos(v, f"{path}[{i}]")]
    return [path] if isinstance(value, str) and "TODO" in value else []


def load_profile(path: Path | None = None) -> Profile:
    if path:
        data = yaml.safe_load(get_settings().path(path).read_text())
    else:
        profile, _ = config_store.raw_section("profile")
        notifications, _ = config_store.raw_section("notifications")
        data = {**profile, "notifications": notifications}
    for field in _find_todos(data):
        log.warning("Profile field %s is still TODO", field)
    return Profile.model_validate(data)
