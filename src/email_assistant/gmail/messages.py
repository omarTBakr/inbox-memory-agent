"""Read messages from Gmail into the Email shape the graphs use (read-only)."""

import base64
import re

from email_assistant.emails import Email, SampleEmail, clean_text
from email_assistant.gmail.actions import GMAIL_PREFIX
from email_assistant.gmail.client import get_service
from email_assistant.settings import get_settings


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _html_to_text(markup: str) -> str:
    return clean_text(re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", markup))


def _body(payload: dict) -> str:
    """Prefer text/plain anywhere in the MIME tree, else text/html converted to text."""
    plain, rich = [], []

    def walk(part: dict):
        data = part.get("body", {}).get("data")
        if data and part.get("mimeType") == "text/plain":
            plain.append(_decode(data))
        elif data and part.get("mimeType") == "text/html":
            rich.append(_html_to_text(_decode(data)))
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return clean_text("\n".join(plain) if plain else "\n".join(rich))


def to_email(message: dict) -> Email:
    headers = {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}
    body = _body(message["payload"]) or message.get("snippet", "")
    return Email(
        author=headers.get("from", ""),
        to=headers.get("to", ""),
        subject=headers.get("subject", ""),
        email_thread=body[: get_settings().gmail_max_body_chars],
        folder="spam" if "SPAM" in message.get("labelIds", []) else "inbox",
    )


def fetch(ids: list[str], gmail=None) -> list[SampleEmail]:
    """Full messages by id, in the given order; nothing is marked read or changed."""
    gmail = gmail or get_service()
    emails = []
    for message_id in ids:
        message = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
        emails.append(SampleEmail(id=f"{GMAIL_PREFIX}{message_id}", expected=None, email=to_email(message)))
    return emails


def recent(count: int, query: str) -> list[SampleEmail]:
    """The `count` most recent messages matching `query` (Spam included when the query says `in:spam`)."""
    gmail = get_service()
    listed = gmail.users().messages().list(
        userId="me", q=query, maxResults=count, includeSpamTrash="in:spam" in query,
    ).execute()
    return fetch([ref["id"] for ref in listed.get("messages", [])], gmail)
