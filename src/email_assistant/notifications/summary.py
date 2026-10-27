"""Build validated notifications from a finished graph run, and render them as text."""

from langchain_core.messages import AIMessage

from email_assistant.graph.common import State
from email_assistant.notifications.schemas import (
    Action,
    DigestItem,
    EmailRef,
    IgnoredDigest,
    NotifiedNotification,
    RespondedNotification,
    email_addresses,
)
from email_assistant.prompts import get_prompt
from email_assistant.tools.email_tools import WRITE_EMAIL

Notification = RespondedNotification | NotifiedNotification


def _tool_calls(state: State) -> list[dict]:
    return [c for m in state.get("messages", []) if isinstance(m, AIMessage) for c in m.tool_calls]


def email_ref(state: State, ref: str) -> EmailRef:
    email = state["email_input"]
    return EmailRef(ref=ref, sender=email["author"], to=email["to"], subject=email["subject"],
                    folder=email.get("folder", "inbox"))


def build(state: State, feedback_id: str, ref: str, tool_names: set[str]) -> Notification:
    """The notification for a 'respond' or 'notify' run, checked against the email and tools."""
    base = {"feedback_id": feedback_id, "email": email_ref(state, ref).model_dump(), "reasoning": state["triage_reasoning"]}
    context = {"known_addresses": email_addresses(state["email_input"]), "tool_names": tool_names}
    if state["classification"] == "respond":
        calls = _tool_calls(state)
        return RespondedNotification.model_validate({
            **base,
            "replies": [c["args"] for c in calls if c["name"] == WRITE_EMAIL],
            "actions": [{"tool": c["name"], "args": c["args"]} for c in calls if c["name"] != WRITE_EMAIL],
            "escalation": state.get("escalation"),
        }, context=context)
    return NotifiedNotification.model_validate({**base, "preview": state["email_input"]["email_thread"]}, context=context)


def digest_item(feedback_id: str, ref: EmailRef, reasoning: str) -> DigestItem:
    return DigestItem(feedback_id=feedback_id, email=ref, reasoning=reasoning)


def _or_none(parts: list[str], sep: str = "\n\n") -> str:
    return sep.join(parts) if parts else get_prompt("notifications/none").compile()


def _warnings(items: list[str]) -> str:
    if not items:
        return ""
    return get_prompt("notifications/warnings").compile(items="\n".join(f"• {w}" for w in items))


def _spam_note(ref: EmailRef) -> str:
    return get_prompt("notifications/spam_note").compile() if ref.folder == "spam" else ""


def _action(action: Action) -> str:
    return f"• {action.tool}: " + ", ".join(f"{k}={v}" for k, v in action.args.items())


def render(notification: Notification | IgnoredDigest) -> str:
    if isinstance(notification, IgnoredDigest):
        item = get_prompt("notifications/digest_item")
        items = [
            item.compile(number=i, sender=d.email.sender, subject=d.email.subject, reasoning=d.reasoning,
                         folder_tag=get_prompt("notifications/spam_tag").compile() if d.email.folder == "spam" else "")
            for i, d in enumerate(notification.items, start=1)
        ]
        return get_prompt("notifications/digest").compile(count=len(items), items="\n".join(items)).strip()
    if isinstance(notification, RespondedNotification):
        reply = get_prompt("notifications/reply_item")
        text = get_prompt("notifications/responded").compile(
            sender=notification.email.sender,
            subject=notification.email.subject,
            reasoning=notification.reasoning,
            escalation=(get_prompt("notifications/escalation").compile(reason=notification.escalation)
                        if notification.escalation else ""),
            replies=_or_none([reply.compile(**r.model_dump()) for r in notification.replies]),
            actions=_or_none([_action(a) for a in notification.actions], sep="\n"),
            warnings=_warnings(notification.warnings),
        )
    else:
        text = get_prompt("notifications/notified").compile(
            classification=notification.classification,
            sender=notification.email.sender,
            subject=notification.email.subject,
            reasoning=notification.reasoning,
            preview=notification.preview,
            warnings=_warnings(notification.warnings),
            folder_note=_spam_note(notification.email),
        )
    return text.strip()
