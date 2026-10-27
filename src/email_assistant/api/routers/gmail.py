from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from email_assistant import config_store
from email_assistant.gmail import client
from email_assistant.settings import get_settings

router = APIRouter(tags=["gmail"])


@router.get("/gmail/status")
async def status():
    secrets = config_store.secret_status("gmail")
    return {
        "client_configured": secrets["client_config"],
        "connected": secrets["token"],
        "redirect_url": get_settings().google_oauth_redirect_url,
        "scopes": client.scopes(),
        "preview_count": get_settings().gmail_preview_count,
    }


@router.post("/gmail/client")
async def upload_client(file: UploadFile):
    kind = await run_in_threadpool(client.save_client_config, (await file.read()).decode())
    return {"ok": True, "client_type": kind}


@router.get("/gmail/oauth/start")
async def oauth_start():
    try:
        return {"url": await run_in_threadpool(client.start_oauth)}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.get("/gmail/oauth/callback", include_in_schema=False)
async def oauth_callback(state: str, code: str | None = None, error: str | None = None):
    result = "error" if error else "connected"
    if not error:
        try:
            await run_in_threadpool(client.finish_oauth, state, code)
        except Exception:
            result = "error"
    return RedirectResponse(f"{get_settings().ui_base_url}/setup/gmail?gmail={result}")


@router.post("/gmail/test")
async def test():
    try:
        return await run_in_threadpool(client.connection_test)
    except Exception as e:
        raise HTTPException(502, f"Gmail: {e}")


@router.post("/gmail/disconnect")
async def disconnect():
    await run_in_threadpool(client.disconnect)
    return {"ok": True}


# ---------- auto-trigger ----------

@router.get("/gmail/watcher")
async def watcher_status():
    from email_assistant.gmail.watcher import watcher

    return await run_in_threadpool(watcher.status)


@router.post("/gmail/watcher/{action}")
async def watcher_action(action: str):
    """on | off: switch auto-trigger (saved in the gmail section); check: check for new mail now."""
    from email_assistant.gmail.watcher import watcher

    if action in ("on", "off"):
        data = config_store.section("gmail").model_dump(mode="json")
        await run_in_threadpool(config_store.save, "gmail", {**data, "auto_trigger": action == "on"})
        if action == "on":
            watcher.start()
            watcher.check_now()
    elif action == "check":
        if not watcher.alive:
            watcher.start()
        watcher.check_now()
    else:
        raise HTTPException(404, "action must be on, off or check")
    return await run_in_threadpool(watcher.status)
