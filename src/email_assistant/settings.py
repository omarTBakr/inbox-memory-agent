"""Typed view of the .env configuration.

Values come from the process environment first (the Makefile exports .env),
then from the .env file itself, then from the defaults below.

Relative paths resolve against PROJECT_ROOT: the source checkout, or the bundled
resources when packaged (APP_RESOURCES, set by the AppImage launcher, which also
points APP_ENV_FILE at the user's own .env in ~/.config/email-assistant).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(os.environ.get("APP_RESOURCES") or Path(__file__).resolve().parents[2])
ENV_FILE = Path(os.environ.get("APP_ENV_FILE") or PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Defaults for the model sections (the UI saves its own choice in Postgres)
    llm_provider: str = "ollama"
    embedding_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "gemma4:e4b"
    llm_temperature: float = 0.0
    llm_num_ctx: int = 8192
    llm_reasoning: bool = False
    embedding_model: str = "nomic-embed-text"
    embedding_dims: int = 768

    # Profile / data / prompts
    user_profile_path: Path = Path("config/user_profile.yml")
    options_path: Path = Path("config/options.yml")
    model_prices_path: Path = Path("config/model_prices.yml")
    guides_path: Path = Path("config/guides.yml")
    setup_guide_doc: Path = Path("docs/SETUP_GUIDE.md")
    sample_emails_path: Path = Path("data/sample_emails.yml")
    prompts_dir: Path = Path("prompts")
    prompt_source: Literal["local", "langfuse"] = "local"
    prompt_label: str = "production"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "email_agent"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "email_memory"
    database_url: SecretStr = SecretStr("")

    # Long-term memory
    memory_namespace: str = "email_assistant"
    memory_semantic_collection: str = "semantic"
    memory_episodic_collection: str = "episodic"
    memory_page_size: int = 100
    episodic_top_k: int = 3
    episodic_min_score: float = 0.75
    memory_procedural_collection: str = "procedural"
    # ReAct reply agent (stage 04)
    react_max_steps: int = 6
    react_max_revisions: int = 1
    react_context_memories: int = 5
    # langmem optimizer strategy: prompt_memory | gradient | metaprompt
    procedural_optimizer_kind: Literal["prompt_memory", "gradient", "metaprompt"] = "prompt_memory"

    # Push notifications (who receives them is in the profile)
    notify_dry_run: bool = True
    notify_max_chars: int = 4000
    notify_preview_chars: int = 300
    notify_reasoning_chars: int = 500
    digest_max_items: int = 10
    notify_timeout_seconds: float = 10.0
    telegram_api_base: str = "https://api.telegram.org"
    telegram_bot_token: SecretStr = SecretStr("")
    # feedback listener: long-polls Telegram for 👍/👎 clicks (runs inside the API, or `make bot`)
    telegram_listener_enabled: bool = True
    telegram_poll_timeout: int = 25

    # Deployment environment: labels Langfuse traces/scores and MLflow runs
    app_env: str = Field("development", pattern=r"^[a-z0-9_-]{1,40}$")

    # Langfuse
    langfuse_enabled: bool = True
    langfuse_host: str = "http://localhost:3000"
    langfuse_embed_url: str = "http://localhost:3002"
    langfuse_init_project_id: str = ""
    visualizations_cache_seconds: float = 60.0
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_encryption_key: SecretStr = SecretStr("")

    # MLflow
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "email-assistant"

    # Gmail worker
    gmail_credentials_path: Path = Path("secrets/credentials.json")
    gmail_token_path: Path = Path("secrets/token.json")
    gmail_poll_seconds: int = 60
    gmail_query: str = "is:unread in:inbox"
    gmail_dry_run: bool = True
    gmail_processed_label: str = "assistant/processed"
    gmail_preview_count: int = 5
    gmail_max_body_chars: int = 4000
    # auto-trigger: watch Gmail for new messages and run the last stage on each
    gmail_watcher_enabled: bool = True
    gmail_auto_trigger: bool = False
    gmail_include_spam: bool = False
    gmail_spam_query: str = "in:spam is:unread"
    gmail_max_per_tick: int = 5
    gmail_max_attempts: int = 3
    gmail_history_fallback_query: str = "newer_than:1d"
    gmail_scopes: list[str] = ["https://www.googleapis.com/auth/gmail.modify"]
    calendar_scopes: list[str] = ["https://www.googleapis.com/auth/calendar"]
    google_oauth_redirect_url: str = "http://localhost:8000/api/gmail/oauth/callback"

    # App / UI
    app_user_id: str = "default"
    app_encryption_key: SecretStr = SecretStr("")
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    ui_port: int = 5173
    ui_base_url: str = "http://localhost:5173"
    config_cache_seconds: float = 5.0
    health_timeout_seconds: float = 3.0

    log_level: str = "INFO"

    @field_validator("app_env")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value.startswith("langfuse"):
            raise ValueError("APP_ENV must not start with 'langfuse' (reserved by Langfuse)")
        return value

    def path(self, value: Path) -> Path:
        """Resolve a configured path relative to the project root."""
        return value if value.is_absolute() else PROJECT_ROOT / value

    def problems(self) -> list[str]:
        """Configuration errors that would stop the app from running."""
        errors = []
        for field in ("ollama_base_url", "llm_model", "embedding_model"):
            if not getattr(self, field):
                errors.append(f"{field.upper()} is empty")
        if not self.database_url.get_secret_value():
            errors.append("DATABASE_URL is empty")
        if not self.path(self.user_profile_path).is_file():
            errors.append(f"USER_PROFILE_PATH not found: {self.user_profile_path}")
        if not self.path(self.prompts_dir).is_dir():
            errors.append(f"PROMPTS_DIR not found: {self.prompts_dir}")
        if self.langfuse_enabled or self.prompt_source == "langfuse":
            if not (self.langfuse_public_key and self.langfuse_secret_key.get_secret_value()):
                errors.append("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are required when Langfuse is used")
            if len(self.langfuse_encryption_key.get_secret_value()) != 64:
                errors.append("LANGFUSE_ENCRYPTION_KEY must be 64 hex chars (openssl rand -hex 32)")
        if not self.app_encryption_key.get_secret_value():
            errors.append("APP_ENCRYPTION_KEY is empty (make env generates one; needed to store secrets)")
        if self.mlflow_enabled and not self.mlflow_tracking_uri:
            errors.append("MLFLOW_TRACKING_URI is required when MLFLOW_ENABLED=true")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
