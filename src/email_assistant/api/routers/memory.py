"""Long-term memory for the UI: browse, search and delete facts (semantic) and labelled examples
(episodic); procedures (triage rules, agent instructions) with their history, and reset to the profile."""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from email_assistant import prompts
from email_assistant.memory import episodic, procedural
from email_assistant.memory.store import get_store, namespace
from email_assistant.profile import load_profile
from email_assistant.settings import get_settings

router = APIRouter(tags=["memory"])

LISTABLE = ("semantic", "episodic")
DELETABLE = (*LISTABLE, "procedural")


def _user_id() -> str:
    return load_profile().user.id


def _namespace(kind: str, user_id: str) -> tuple[str, ...]:
    if kind == "semantic":
        return namespace(user_id, get_settings().memory_semantic_collection)
    if kind == "episodic":
        return episodic.episodic_namespace(user_id)
    if kind == "procedural":
        return procedural.procedural_namespace(user_id)
    raise HTTPException(400, f"Unknown memory kind {kind!r}")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _list(kind: str, q: str | None, limit: int, offset: int) -> dict:
    if kind not in LISTABLE:
        raise HTTPException(400, f"Memory kind must be one of {', '.join(LISTABLE)}")
    with get_store() as store:
        # with a query: ranked by embedding similarity; without: most recently updated first
        found = store.search(_namespace(kind, _user_id()), query=q or None, limit=limit + 1, offset=offset)
    items = [{
        "key": item.key,
        "value": item.value,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "score": getattr(item, "score", None),
    } for item in found[:limit]]
    return {"items": items, "has_more": len(found) > limit}


def _delete(kind: str, key: str) -> None:
    if kind not in DELETABLE:
        raise HTTPException(400, f"Memory kind must be one of {', '.join(DELETABLE)}")
    ns = _namespace(kind, _user_id())
    with get_store() as store:
        if store.get(ns, key) is None:
            raise HTTPException(404, f"No {kind} memory {key!r}")
        store.delete(ns, key)


def _procedures() -> list[dict]:
    profile = load_profile()
    user_id = profile.user.id
    seeds = procedural.profile_procedures(profile)
    with get_store() as store:
        ns = procedural.procedural_namespace(user_id)
        rows = []
        for name, seed in seeds.items():
            item = store.get(ns, name)
            value = item.value if item else {}
            rows.append({
                "name": name,
                "prompt": value.get("prompt", seed),
                "profile_prompt": seed,
                "version": value.get("version"),  # None: still the profile's text
                "updated_at": value.get("updated_at"),
                "feedback": value.get("feedback"),
            })
    return rows


def _history(name: str) -> dict:
    profile = load_profile()
    seeds = procedural.profile_procedures(profile)
    if name not in seeds:
        raise HTTPException(404, f"Unknown procedure {name!r}")
    if not get_settings().langfuse_enabled:
        return {"name": name, "profile_prompt": seeds[name], "versions": [], "note": "Langfuse is disabled: no history kept."}
    try:
        versions = prompts.history(f"procedural/{profile.user.id}/{name}")
    except Exception as e:  # never rewritten yet (no such prompt), or Langfuse unreachable
        if "not found" in str(e).lower() or "404" in str(e):
            versions = []
        else:
            raise HTTPException(502, f"Could not read the history from Langfuse: {e}") from e
    return {"name": name, "profile_prompt": seeds[name], "versions": versions[::-1]}  # newest first


@router.get("/memory/procedures")
async def procedures():
    return await run_in_threadpool(_procedures)


@router.get("/memory/procedures/{name}/history")
async def procedure_history(name: str):
    return await run_in_threadpool(_history, name)


@router.get("/memory/{kind}")
async def list_memories(kind: str, q: str | None = None, limit: int = 50, offset: int = 0):
    return await run_in_threadpool(_list, kind, q, max(1, min(limit, 200)), max(0, offset))


@router.delete("/memory/{kind}/{key}")
async def delete_memory(kind: str, key: str):
    """Forget one memory. For a procedure this resets it to the profile's text."""
    await run_in_threadpool(_delete, kind, key)
    return {"deleted": key}
