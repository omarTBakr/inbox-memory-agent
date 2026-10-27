"""The few changes the app makes in Gmail, each only on an explicit user action."""

from email_assistant.gmail.client import get_service

GMAIL_PREFIX = "gmail:"


def message_id(email_ref: str) -> str:
    """Gmail message id from a feedback row's email_ref ("gmail:<id>")."""
    if not email_ref.startswith(GMAIL_PREFIX):
        raise ValueError(f"{email_ref!r} is not a Gmail message")
    return email_ref.removeprefix(GMAIL_PREFIX)


def not_spam(email_ref: str) -> None:
    """Move a message from Spam back to the Inbox (what Gmail's own "Not spam" button does)."""
    get_service().users().messages().modify(
        userId="me", id=message_id(email_ref), body={"removeLabelIds": ["SPAM"], "addLabelIds": ["INBOX"]},
    ).execute()
