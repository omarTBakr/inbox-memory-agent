"""Typed notifications: every message the user receives is built from one of these models.

Facts (sender, subject, recipients, preview) are copied from the email and the tool calls,
never from model prose. Validators cross-check what the agent did against the email and
the tools it actually has; anything suspicious becomes a visible warning in the message
instead of being passed on silently. Checks need context, passed at validation time:
  known_addresses  every address that appears in the email (from, to, body)
  tool_names       tools the agent really has
"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, ValidationInfo, field_validator, model_validator

from email_assistant.emails import Email, Folder, clean_text
from email_assistant.settings import get_settings

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# free text shown to the user: never passes on HTML comments or tags, whatever the source
UserText = Annotated[str, AfterValidator(clean_text)]


def addresses(text: str) -> set[str]:
    return {a.lower() for a in ADDRESS.findall(text or "")}


def email_addresses(email: Email) -> set[str]:
    return addresses(" ".join([email["author"], email["to"], email["email_thread"]]))


class EmailRef(BaseModel):
    """The email a notification is about, as received (not as described by the model)."""

    ref: str = Field(description="Gmail message id or sample id")
    sender: str
    to: str
    subject: str
    folder: Folder = "inbox"


class SentReply(BaseModel):
    to: str
    subject: str
    content: UserText = Field(min_length=1)

    @field_validator("to")
    @classmethod
    def _one_address(cls, value: str) -> str:
        if not addresses(value):
            raise ValueError(f"reply recipient {value!r} is not an email address")
        return value


class Action(BaseModel):
    tool: str
    args: dict


class _Base(BaseModel):
    feedback_id: str
    email: EmailRef
    reasoning: UserText
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _never_answer_spam(self):
        if self.email.folder == "spam" and isinstance(self, RespondedNotification) and self.replies:
            self.warnings.append("A reply was written to an email from Spam.")
        return self

    @field_validator("reasoning")
    @classmethod
    def _short_reasoning(cls, value: str) -> str:
        limit = get_settings().notify_reasoning_chars
        value = " ".join(value.split())
        return value if len(value) <= limit else value[: limit - 1] + "…"


class RespondedNotification(_Base):
    """The assistant answered an email on the user's behalf."""

    kind: Literal["responded"] = "responded"
    classification: Literal["respond"] = "respond"
    replies: list[SentReply]
    actions: list[Action] = Field(default_factory=list)
    # set when the agent sent a holding reply instead of answering
    escalation: UserText | None = None

    @model_validator(mode="after")
    def _check_against_email(self, info: ValidationInfo):
        ctx = info.context or {}
        known = ctx.get("known_addresses", set())
        tools = ctx.get("tool_names")
        if not self.replies:
            self.warnings.append("Classified as 'respond' but no reply was written.")
        for reply in self.replies:
            for address in addresses(reply.to) - known:
                self.warnings.append(f"Reply sent to {address}, who does not appear in the email.")
        if tools is not None:
            for action in self.actions:
                if action.tool not in tools:
                    self.warnings.append(f"Unknown tool '{action.tool}' was called.")
        return self


class NotifiedNotification(_Base):
    """An email the user should know about; no reply was sent."""

    kind: Literal["notified"] = "notified"
    classification: Literal["notify"] = "notify"
    preview: UserText

    @field_validator("preview")
    @classmethod
    def _short_preview(cls, value: str) -> str:
        return value[: get_settings().notify_preview_chars]


class DigestItem(BaseModel):
    feedback_id: str
    email: EmailRef
    reasoning: UserText


class IgnoredDigest(BaseModel):
    """Emails the assistant ignored, sent together so wrong 'ignore' decisions can be caught."""

    kind: Literal["ignored_digest"] = "ignored_digest"
    items: list[DigestItem] = Field(min_length=1)
