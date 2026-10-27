"""The email shape every graph works on, plus the offline sample set."""

import html
import re
from dataclasses import dataclass
from typing import Literal

import yaml
from typing_extensions import NotRequired, TypedDict

from email_assistant.settings import get_settings

Classification = Literal["ignore", "notify", "respond"]
Folder = Literal["inbox", "spam"]

_MARKUP = re.compile(r"(?is)<!--(?:>|.*?-->)|<(script|style|head|title)\b.*?</\1\s*>|<![^<>]*>|</?[a-z][^<>]*>")
_INVISIBLE = re.compile(r"[\u00ad\u034f\u200b\u2060\ufeff]|(?<!\w)\u200c|\u200c(?!\w)")


def clean_text(text: str) -> str:
    """Plain text without HTML comments, tags or invisible padding, even if the markup arrived escaped."""
    text = _MARKUP.sub("", html.unescape(_MARKUP.sub("", text)))
    text = re.sub(r"[^\S\n]+", " ", _INVISIBLE.sub("", text))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r" *\n *", "\n", text)).strip()


class Email(TypedDict):
    author: str
    to: str
    subject: str
    email_thread: str
    # Gmail folder it was found in; "spam" emails are never answered (notify at most)
    folder: NotRequired[Folder]


@dataclass
class SampleEmail:
    id: str
    # the right label when known (sample set); None for real inbox emails
    expected: Classification | None
    email: Email


def load_sample_emails() -> list[SampleEmail]:
    s = get_settings()
    data = yaml.safe_load(s.path(s.sample_emails_path).read_text())
    return [
        SampleEmail(
            id=e["id"],
            expected=e["expected"],
            email=Email(author=e["from"], to=e["to"], subject=e["subject"], email_thread=e["body"]),
        )
        for e in data["emails"]
    ]
