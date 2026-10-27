"""Gmail API access: OAuth (web flow for the UI, local flow for the CLI) and the API client.

The OAuth client JSON and the token are secrets of the `gmail` section (encrypted in
Postgres); the files at GMAIL_CREDENTIALS_PATH / GMAIL_TOKEN_PATH are used as fallback.
Scopes come from the `gmail` section, plus the `calendar` scopes when calendar is enabled.
"""

import json
import os
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from googleapiclient.discovery import build

from email_assistant import config_store
from email_assistant.settings import get_settings

# OAuth flows waiting for Google's redirect, by state
_pending: dict[str, Flow] = {}


def scopes() -> list[str]:
    calendar = config_store.section("calendar")
    return config_store.section("gmail").scopes + (calendar.scopes if calendar.enabled else [])


def client_config() -> dict:
    saved = config_store.secret("gmail", "client_config")
    if saved:
        return json.loads(saved)
    s = get_settings()
    path = s.path(s.gmail_credentials_path)
    if path.exists():
        return json.loads(path.read_text())
    raise RuntimeError("No Google OAuth client configured: upload the client JSON first")


def save_client_config(raw: str) -> str:
    """Validate and store the OAuth client JSON downloaded from Google Cloud; returns its type."""
    data = json.loads(raw)
    kind = next((k for k in ("web", "installed") if k in data), None)
    if not kind or not {"client_id", "client_secret"} <= data[kind].keys():
        raise ValueError("Not a Google OAuth client file (expected a 'web' or 'installed' client)")
    config_store.set_secret("gmail", "client_config", json.dumps(data))
    return kind


def start_oauth() -> str:
    """URL of Google's consent page; Google redirects back to GOOGLE_OAUTH_REDIRECT_URL."""
    flow = Flow.from_client_config(client_config(), scopes=scopes(),
                                   redirect_uri=get_settings().google_oauth_redirect_url)
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    _pending[state] = flow
    return url


def finish_oauth(state: str, code: str) -> None:
    flow = _pending.pop(state, None)
    if flow is None:
        raise ValueError("Unknown or expired OAuth state; start the connection again")
    if urlparse(get_settings().google_oauth_redirect_url).hostname in ("localhost", "127.0.0.1"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # http is fine for a loopback redirect
    flow.fetch_token(code=code)
    config_store.set_secret("gmail", "token", flow.credentials.to_json())


def disconnect() -> None:
    config_store.delete_secret("gmail", "token")


def authorize() -> None:
    """CLI alternative: browser OAuth via a temporary local server."""
    flow = InstalledAppFlow.from_client_config(client_config(), scopes())
    creds = flow.run_local_server(port=0)
    config_store.set_secret("gmail", "token", creds.to_json())


def _credentials() -> Credentials:
    token = config_store.secret("gmail", "token")
    if not token:
        s = get_settings()
        path = s.path(s.gmail_token_path)
        if not path.exists():
            raise RuntimeError("Gmail is not connected")
        token = path.read_text()
    creds = Credentials.from_authorized_user_info(json.loads(token), scopes())
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config_store.set_secret("gmail", "token", creds.to_json())
    return creds


def get_service():
    """Authenticated Gmail API client."""
    return build("gmail", "v1", credentials=_credentials(), cache_discovery=False)


def connection_test() -> dict:
    gmail = get_service()
    profile = gmail.users().getProfile(userId="me").execute()
    inbox = gmail.users().labels().get(userId="me", id="INBOX").execute()
    return {
        "email": profile["emailAddress"],
        "messages_total": profile.get("messagesTotal"),
        "inbox_unread": inbox.get("messagesUnread"),
    }
