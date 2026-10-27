"""Prompt registry.

prompts/ holds one YAML file per prompt (the source of truth, versioned in git).
Langfuse keeps the version history: `push` creates a new version only when a
prompt's template or config changed, and procedural memory writes its optimized
prompts there as new versions too. At runtime PROMPT_SOURCE picks local files
or the PROMPT_LABEL version from Langfuse.

Templates use {{variable}} placeholders (Langfuse syntax).
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from email_assistant.settings import get_settings

_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass
class PromptSpec:
    name: str
    template: str
    type: str = "text"
    description: str = ""
    variables: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    source: str = "local"
    langfuse_prompt: Any = None

    def compile(self, **values: Any) -> str:
        missing = set(_VAR.findall(self.template)) - values.keys()
        if missing:
            raise KeyError(f"Prompt {self.name!r} is missing variables: {sorted(missing)}")
        return _VAR.sub(lambda m: str(values[m.group(1)]), self.template)

    @property
    def digest(self) -> str:
        payload = yaml.safe_dump({"template": self.template, "config": self.config}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _prompts_dir() -> Path:
    s = get_settings()
    return s.path(s.prompts_dir)


def _file_for(name: str) -> Path:
    return _prompts_dir() / f"{name}.yml"


def load_local(name: str) -> PromptSpec:
    data = yaml.safe_load(_file_for(name).read_text())
    if data.get("name") != name:
        raise ValueError(f"{_file_for(name)} declares name {data.get('name')!r}, expected {name!r}")
    return PromptSpec(**data)


def list_local() -> list[str]:
    root = _prompts_dir()
    return sorted(str(p.relative_to(root).with_suffix("")) for p in root.rglob("*.yml"))


def _langfuse():
    from email_assistant.tracing import langfuse_client

    return langfuse_client()


def _fetch_langfuse(name: str, *, label: str | None = None, version: int | None = None) -> PromptSpec:
    # prompts written at runtime (procedural memory) have no local file
    local = load_local(name) if _file_for(name).exists() else PromptSpec(name=name, template="")
    remote = _langfuse().get_prompt(name, label=label, version=version, type=local.type, cache_ttl_seconds=0)
    return PromptSpec(
        name=name,
        template=remote.prompt,
        type=local.type,
        description=local.description,
        variables=local.variables,
        config=remote.config or {},
        version=remote.version,
        source="langfuse",
        langfuse_prompt=remote,
    )


def get_prompt(name: str) -> PromptSpec:
    """The prompt to use at runtime, according to PROMPT_SOURCE."""
    s = get_settings()
    if s.prompt_source == "langfuse":
        return _fetch_langfuse(name, label=s.prompt_label)
    return load_local(name)


def push(name: str, commit_message: str | None = None) -> str:
    """Create a new Langfuse version of `name` if the local file differs from the latest one."""
    local = load_local(name)
    try:
        latest = _fetch_langfuse(name, label="latest")
        if latest.digest == local.digest:
            return f"{name}: unchanged (v{latest.version})"
    except Exception:  # not in Langfuse yet
        latest = None
    created = _langfuse().create_prompt(
        name=name,
        type=local.type,
        prompt=local.template,
        config=local.config,
        labels=[get_settings().prompt_label],
        commit_message=commit_message or f"sync from prompts/ ({local.digest})",
    )
    return f"{name}: {'created' if latest is None else 'updated'} -> v{created.version}"


def record_version(name: str, text: str, commit_message: str) -> int | None:
    """Store `text` as a new Langfuse version of `name` (history for runtime-written prompts)."""
    if not get_settings().langfuse_enabled:
        return None
    created = _langfuse().create_prompt(
        name=name, type="text", prompt=text, labels=[get_settings().prompt_label], commit_message=commit_message,
    )
    return created.version


def pull(name: str) -> str:
    """Overwrite the local file's template/config with the PROMPT_LABEL version from Langfuse."""
    remote = _fetch_langfuse(name, label=get_settings().prompt_label)
    path = _file_for(name)
    data = yaml.safe_load(path.read_text())
    if data["template"] == remote.template and data.get("config", {}) == remote.config:
        return f"{name}: up to date (v{remote.version})"
    data.update(template=remote.template, config=remote.config)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return f"{name}: pulled v{remote.version}"


def history(name: str) -> list[dict[str, Any]]:
    """All Langfuse versions of `name`, oldest first."""
    client = _langfuse()
    metas = client.api.prompts.list(name=name).data
    versions = sorted(v for meta in metas if meta.name == name for v in meta.versions)
    rows = []
    for version in versions:
        p = _fetch_langfuse(name, version=version)
        rows.append({
            "version": version,
            "labels": list(getattr(p.langfuse_prompt, "labels", []) or []),
            "commit_message": getattr(p.langfuse_prompt, "commit_message", None),
            "digest": p.digest,
        })
    return rows
