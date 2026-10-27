from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from email_assistant import config_store
from email_assistant.config_models import SECRETS, SECTIONS

router = APIRouter(tags=["config"])


class SaveRequest(BaseModel):
    data: dict
    # secret name -> new value; omitted or empty keeps the stored one
    secrets: dict[str, str] = {}


def _section(name: str) -> type[BaseModel]:
    if name not in SECTIONS:
        raise HTTPException(404, f"Unknown section {name!r}")
    return SECTIONS[name]


@router.get("/schema/{section}")
async def schema(section: str):
    model = _section(section)
    return {
        "schema": model.model_json_schema(),
        # secrets set by a login/upload flow get no input field
        "secrets": [
            {"name": n, "description": meta["description"]}
            for n, meta in SECRETS.get(section, {}).items() if not meta.get("managed")
        ],
    }


@router.get("/config/{section}")
async def get_config(section: str):
    _section(section)

    def load():
        data, source = config_store.raw_section(section)
        # validated + defaults filled in, so the form shows effective values
        try:
            data = SECTIONS[section].model_validate(data).model_dump(mode="json")
            valid, errors = True, []
        except Exception as e:
            valid, errors = False, getattr(e, "errors", lambda **_: [str(e)])(include_url=False, include_context=False)
        return {
            "data": data,
            "source": source,
            "meta": config_store.saved_meta(section),
            "valid": valid,
            "errors": errors,
            "secrets": config_store.secret_status(section),
        }

    return await run_in_threadpool(load)


@router.put("/config/{section}")
async def save_config(section: str, body: SaveRequest):
    _section(section)

    def save():
        # secrets first: they stay stored even if the form is still incomplete
        # (e.g. the Telegram token is needed to detect the chat id the form requires)
        _store_secrets(section, body.secrets)
        version = config_store.save(section, body.data)
        return {"version": version, "secrets": config_store.secret_status(section)}

    return await run_in_threadpool(save)


def _store_secrets(section: str, secrets: dict[str, str]) -> None:
    for name, value in secrets.items():
        if value:
            config_store.set_secret(section, name, value)


class SecretsRequest(BaseModel):
    secrets: dict[str, str]


@router.put("/config/{section}/secrets")
async def save_secrets(section: str, body: SecretsRequest):
    """Store secrets without saving (or validating) the rest of the section."""
    _section(section)
    await run_in_threadpool(_store_secrets, section, body.secrets)
    return {"secrets": config_store.secret_status(section)}


@router.delete("/config/{section}/secrets/{name}")
async def delete_secret(section: str, name: str):
    _section(section)
    await run_in_threadpool(config_store.delete_secret, section, name)
    return {"secrets": config_store.secret_status(section)}


@router.get("/config/{section}/history")
async def history(section: str):
    _section(section)
    return await run_in_threadpool(config_store.history, section)
