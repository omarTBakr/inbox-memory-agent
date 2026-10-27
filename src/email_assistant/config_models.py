"""Configuration sections the UI edits, as pydantic models.

These are the single source of truth for the UI forms: a field without a default is
required, a field with one is optional, `description` is the help text, and
`json_schema_extra={"ui": ...}` carries UI hints:
  options       name of an option list served by GET /api/options/<name>
  custom        True: pick from the options or type your own; False: options only
  secret        stored encrypted, never sent back to the browser
  multiline     render as a text area
  required_if   {"field": ..., "contains": ...}: required when another field has that value
  required      True: has a default, but the user must confirm a choice (shown as required)
Defaults that also exist in .env are read from settings, so values are never duplicated.
"""

from functools import lru_cache
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from email_assistant.emails import Classification
from email_assistant.settings import get_settings


def ui(**hints: Any) -> dict:
    return {"ui": hints}


@lru_cache
def options() -> dict:
    s = get_settings()
    return yaml.safe_load(s.path(s.options_path).read_text())


# ---------- profile ----------

class WorkingHours(BaseModel):
    start: str = Field(pattern=r"^\d{2}:\d{2}$", description="Start of the working day (HH:MM)")
    end: str = Field(pattern=r"^\d{2}:\d{2}$", description="End of the working day (HH:MM)")
    days: list[str] = Field(description="Working days", json_schema_extra=ui(options="weekdays", custom=False))


class User(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", description="Short id for your memory (letters, digits, _ or -)")
    name: str = Field(description="Name the assistant uses for you, e.g. Omar")
    full_name: str = Field(description="Your full name")
    email: str = Field(description="Your email address")
    user_profile_background: str = Field(
        description="One or two sentences on your role and context; helps triage and replies",
        json_schema_extra=ui(multiline=True),
    )
    role: str = Field("", description="Job title")
    organization: str = Field("", description="Company or organisation")
    timezone: str = Field(description="Your time zone", json_schema_extra=ui(options="timezones", custom=False))
    working_hours: WorkingHours
    languages: list[str] = Field(
        default_factory=lambda: ["en"], description="Languages you write emails in",
        json_schema_extra=ui(options="languages", custom=True),
    )


class WritingStyle(BaseModel):
    tone: str = Field(description="How replies should sound", json_schema_extra=ui(options="tones", custom=True))
    signature: str = Field(description="Sign-off added to emails", json_schema_extra=ui(multiline=True))
    preferences: list[str] = Field(
        default_factory=list, description="Extra writing rules, e.g. 'no exclamation marks'",
    )


class Contact(BaseModel):
    name: str = Field(description="Name")
    email: str = Field(description="Email address")
    relation: str = Field("", description="e.g. manager, client, teammate")


class Contacts(BaseModel):
    vip: list[Contact] = Field(default_factory=list, description="Always handled with priority")
    team: list[Contact] = Field(default_factory=list, description="Your team")
    blocked: list[Contact] = Field(default_factory=list, description="Always ignored")


class TriageRules(BaseModel):
    ignore: str = Field(description="Emails to ignore", json_schema_extra=ui(multiline=True))
    notify: str = Field(description="Emails to tell you about without replying", json_schema_extra=ui(multiline=True))
    respond: str = Field(description="Emails the assistant should answer", json_schema_extra=ui(multiline=True))


class Scheduling(BaseModel):
    default_meeting_minutes: int = Field(
        description="Default meeting length", json_schema_extra=ui(options="meeting_minutes", custom=True),
    )
    buffer_minutes: int = Field(
        description="Free time kept between meetings", json_schema_extra=ui(options="buffer_minutes", custom=True),
    )
    no_meetings: list[str] = Field(default_factory=list, description="Times never to book, e.g. 'Fri all day'")


class ProfileSection(BaseModel):
    """Who the assistant works for."""

    user: User
    writing_style: WritingStyle
    contacts: Contacts = Field(default_factory=Contacts)
    triage_rules: TriageRules = Field(description="Starting rules; procedural memory refines them from your feedback")
    agent_instructions: str = Field(
        description="Starting instructions for the reply agent", json_schema_extra=ui(multiline=True),
    )
    escalate_when: list[str] = Field(
        default_factory=list,
        description="Topics the assistant never answers itself: it sends a short holding reply and flags the email to you",
    )
    scheduling: Scheduling


# ---------- notifications ----------

Channel = Literal["telegram", "telegram_self"]


class Notifications(BaseModel):
    """Where the assistant pushes summaries of what it did.

    telegram: your bot messages you (your phone notifies you).
    telegram_self: posted from your own account into Saved Messages (a private log;
    Telegram doesn't notify you about your own messages).
    """

    channels: list[Channel] = Field(description="Channels to push to")
    notify_on: list[Classification] = Field(description="Triage outcomes that trigger a push")
    dry_run: bool = Field(
        default_factory=lambda: get_settings().notify_dry_run,
        description="Print notifications instead of sending them",
    )
    ignored_digest: bool = Field(
        True, description="Send a daily digest of ignored emails, with 👍/👎, to catch wrong 'ignore' decisions",
    )
    digest_time: str = Field(
        "18:00", pattern=r"^\d{2}:\d{2}$", description="When the daily digest is sent (HH:MM, your time zone)",
    )
    telegram_chat_id: str = Field(
        "", description="Your chat id with the bot (send it /start, then use 'Detect')",
        json_schema_extra=ui(required_if={"field": "channels", "contains": "telegram"}),
    )
    telegram_api_id: str = Field(
        "", pattern=r"^\d*$", description="Your Telegram app's api_id (my.telegram.org > API development tools)",
        json_schema_extra=ui(required_if={"field": "channels", "contains": "telegram_self"}),
    )
    telegram_phone: str = Field(
        "", pattern=r"^(\+\d{8,15})?$", description="Phone number of your Telegram account, with +, e.g. +201001234567",
        json_schema_extra=ui(required_if={"field": "channels", "contains": "telegram_self"}),
    )

    @model_validator(mode="after")
    def _channel_fields(self):
        if "telegram" in self.channels and not self.telegram_chat_id:
            raise ValueError("telegram_chat_id is required when telegram is a channel")
        if "telegram_self" in self.channels and not (self.telegram_api_id and self.telegram_phone):
            raise ValueError("telegram_api_id and telegram_phone are required when telegram_self is a channel")
        return self


class Profile(ProfileSection):
    notifications: Notifications


# ---------- gmail / calendar ----------

class GmailConfig(BaseModel):
    """How the assistant works with your inbox."""

    approval_mode: Literal["draft_only", "approve", "auto_send"] = Field(
        "draft_only",
        description="draft_only: replies saved as Gmail drafts; approve: you confirm each reply; auto_send: sent directly",
        json_schema_extra=ui(required=True),
    )
    auto_trigger: bool = Field(
        default_factory=lambda: get_settings().gmail_auto_trigger,
        description="Watch for new emails and handle each one automatically as it arrives",
    )
    query: str = Field(default_factory=lambda: get_settings().gmail_query, description="Gmail search for emails to process")
    include_spam: bool = Field(
        default_factory=lambda: get_settings().gmail_include_spam,
        description="Also check new Spam: such emails are reported to you at most, never answered",
    )
    spam_query: str = Field(
        default_factory=lambda: get_settings().gmail_spam_query, description="Gmail search for Spam emails to check",
    )
    poll_seconds: int = Field(default_factory=lambda: get_settings().gmail_poll_seconds, ge=10, description="How often to check")
    max_per_tick: int = Field(
        default_factory=lambda: get_settings().gmail_max_per_tick, ge=1, le=50,
        description="Most emails handled per check (the rest wait for the next one)",
    )
    processed_label: str = Field(
        default_factory=lambda: get_settings().gmail_processed_label, description="Label added to handled emails",
    )
    scopes: list[str] = Field(default_factory=lambda: get_settings().gmail_scopes, description="Gmail permissions requested")


class CalendarConfig(BaseModel):
    """Google Calendar, used for availability and booking."""

    enabled: bool = Field(False, description="Use Google Calendar (asks for calendar access when connecting Gmail)")
    calendar_id: str = Field("primary", description="Calendar to read and book in")
    scopes: list[str] = Field(
        default_factory=lambda: get_settings().calendar_scopes, description="Calendar permissions requested",
    )


# ---------- models ----------

def _check_provider(value: str, *, embeddings: bool = False) -> str:
    providers = options()["providers"]
    if value not in providers:
        raise ValueError(f"unknown provider {value!r}; choose from {', '.join(providers)}")
    if embeddings and not providers[value].get("embeddings"):
        raise ValueError(f"{value} has no embedding models")
    return value


class ModelConfig(BaseModel):
    """The chat model used for triage, replies and memory."""

    provider: str = Field(
        default_factory=lambda: get_settings().llm_provider,
        description="Local (Ollama) or an API provider", json_schema_extra=ui(options="providers", custom=False, required=True),
    )
    model: str = Field(
        default_factory=lambda: get_settings().llm_model,
        description="Model name", json_schema_extra=ui(options="models", custom=True, required=True),
    )
    base_url: str = Field("", description="API root; empty uses the provider default")
    temperature: float = Field(default_factory=lambda: get_settings().llm_temperature, ge=0, le=2)
    num_ctx: int = Field(default_factory=lambda: get_settings().llm_num_ctx, description="Context window (Ollama only)")
    reasoning: bool = Field(
        default_factory=lambda: get_settings().llm_reasoning, description="Thinking mode for reasoning models (slower)",
    )
    structured_output_method: Literal["json_schema", "function_calling", "json_mode"] | None = Field(
        None, description="How structured answers are requested; empty uses the provider default",
    )

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        return _check_provider(value)

    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.provider == "ollama":
            return get_settings().ollama_base_url
        return options()["providers"][self.provider]["base_url"]

    def resolved_structured_output(self) -> str:
        return self.structured_output_method or options()["providers"][self.provider]["structured_output"]


class EmbeddingsConfig(BaseModel):
    """The embedding model used to search memory."""

    provider: str = Field(
        default_factory=lambda: get_settings().embedding_provider,
        description="Where embeddings are computed", json_schema_extra=ui(options="embedding_providers", custom=False, required=True),
    )
    model: str = Field(
        default_factory=lambda: get_settings().embedding_model,
        description="Embedding model", json_schema_extra=ui(options="embedding_models", custom=True, required=True),
    )
    dims: int = Field(
        default_factory=lambda: get_settings().embedding_dims,
        description="Vector size; changing it requires re-indexing memory", json_schema_extra=ui(required=True),
    )
    base_url: str = Field("", description="API root; empty uses the provider default")

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        return _check_provider(value, embeddings=True)

    def resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.provider == "ollama":
            return get_settings().ollama_base_url
        return options()["providers"][self.provider]["base_url"]


SECTIONS: dict[str, type[BaseModel]] = {
    "profile": ProfileSection,
    "notifications": Notifications,
    "gmail": GmailConfig,
    "calendar": CalendarConfig,
    "model": ModelConfig,
    "embeddings": EmbeddingsConfig,
}

# Secrets per section: name -> help text and whether a flow sets it (no input field).
# Values live encrypted in app_secrets.
SECRETS: dict[str, dict[str, dict]] = {
    "notifications": {
        "telegram_bot_token": {"description": "Token from @BotFather"},
        "telegram_api_hash": {"description": "Your Telegram app's api_hash (my.telegram.org)"},
        "telegram_session": {"description": "Telegram account login", "managed": True},
    },
    "model": {"api_key": {"description": "API key for the selected provider"}},
    "embeddings": {"api_key": {"description": "API key for the embedding provider (if not Ollama)"}},
    "gmail": {
        "client_config": {"description": "OAuth client JSON from Google Cloud", "managed": True},
        "token": {"description": "OAuth token (set by Connect)", "managed": True},
    },
}
