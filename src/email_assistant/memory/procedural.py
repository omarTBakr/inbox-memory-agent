"""Procedural memory: the triage rules and agent instructions, rewritten from user feedback.

Live values are per user in the store under (MEMORY_NAMESPACE, <user id>, procedural),
seeded from the profile. Each rewrite is also recorded as a Langfuse prompt version
named procedural/<user id>/<target> so the history is visible there.
Which targets exist, and when each may change, is configured in prompts/procedural/optimizer.yml.
"""

from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_store
from langgraph.store.base import BaseStore
from langmem import create_prompt_optimizer
from pydantic import BaseModel, Field, create_model

from email_assistant.llm import get_chat_model, structured_output_method
from email_assistant.memory.store import USER_ID_KEY, namespace
from email_assistant.profile import Profile
from email_assistant.prompts import get_prompt, record_version
from email_assistant.settings import get_settings

Procedures = dict[str, str]


def procedural_namespace(user_id: str) -> tuple[str, ...]:
    return namespace(user_id, get_settings().memory_procedural_collection)


def profile_procedures(profile: Profile) -> Procedures:
    """Starting values, from the profile."""
    rules = profile.triage_rules
    return {
        "triage_ignore": rules.ignore,
        "triage_notify": rules.notify,
        "triage_respond": rules.respond,
        "agent_instructions": profile.agent_instructions,
    }


def load(store: BaseStore, user_id: str, profile: Profile) -> Procedures:
    current = profile_procedures(profile)
    for item in store.search(procedural_namespace(user_id), limit=len(current)):
        current[item.key] = item.value["prompt"]
    return current


def from_store(profile: Profile):
    """ProceduresFn for the graph: read the live values on every run."""

    def procedures(config: RunnableConfig) -> Procedures:
        return load(get_store(), config["configurable"][USER_ID_KEY], profile)

    return procedures


def save(store: BaseStore, user_id: str, name: str, prompt: str, feedback: str) -> int:
    ns = procedural_namespace(user_id)
    previous = store.get(ns, name)
    version = previous.value["version"] + 1 if previous else 1
    store.put(ns, name, {
        "prompt": prompt,
        "version": version,
        "feedback": feedback,
        "updated_at": datetime.now(UTC).isoformat(),
    }, index=False)
    record_version(f"procedural/{user_id}/{name}", prompt, commit_message=f"v{version}: {feedback}")
    return version


def compact_trajectory(trajectory: list) -> list[dict]:
    """Plain role/content turns: tool calls and results as text keep small models on track."""
    turns = []
    for m in trajectory:
        if not isinstance(m, BaseMessage):
            turns.append(m)
            continue
        text = m.content if isinstance(m.content, str) else str(m.content)
        calls = [f"[called {c['name']}({c['args']})]" for c in getattr(m, "tool_calls", [])]
        if m.type == "tool":
            text = f"[{m.name} returned] {text}"
        content = "\n".join(part for part in [text, *calls] if part)
        if content:
            turns.append({"role": "user" if m.type == "human" else "assistant", "content": content})
    return turns


def _select(targets: list[dict], current: Procedures, turns: list[dict], feedback: str) -> list[str]:
    """Which targets the feedback is about (strict JSON output, reliable with local models)."""
    names = tuple(t["name"] for t in targets)
    Selection = create_model(
        "Selection",
        __base__=BaseModel,
        reasoning=(str, Field(description="Why these procedures, and not the others.")),
        which=(list[Literal[names]], Field(description="Names of the procedures to update; may be empty.")),
    )
    prompt = get_prompt("procedural/select").compile(
        trajectory="\n\n".join(f"{t['role']}: {t['content']}" for t in turns),
        feedback=feedback,
        targets="\n\n".join(f"- {t['name']}: {current[t['name']]}\n  When to update: {t['when_to_update']}" for t in targets),
    )
    model = get_chat_model().with_structured_output(Selection, method=structured_output_method())
    return list(dict.fromkeys(model.invoke(prompt).which))


def optimize(store: BaseStore, user_id: str, profile: Profile, trajectory: list, feedback: str) -> list[dict]:
    """Rewrite the procedures this feedback is about; returns the changes."""
    spec = get_prompt("procedural/optimizer")
    targets = {t["name"]: t for t in spec.config["targets"]}
    current = load(store, user_id, profile)
    turns = compact_trajectory(trajectory)
    optimizer = create_prompt_optimizer(get_chat_model(), kind=get_settings().procedural_optimizer_kind)
    changes = []
    for name in _select(list(targets.values()), current, turns, feedback):
        t = targets[name]
        after = optimizer.invoke({
            "trajectories": [(turns, spec.compile(feedback=feedback))],
            "prompt": {
                "name": name,
                "prompt": current[name],
                "update_instructions": t["update_instructions"],
                "when_to_update": t["when_to_update"],
            },
        })
        if after.strip() != current[name].strip():
            version = save(store, user_id, name, after, feedback)
            changes.append({"name": name, "before": current[name], "after": after, "version": version})
    return changes
