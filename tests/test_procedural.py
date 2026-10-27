import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from email_assistant.emails import load_sample_emails
from email_assistant.memory.procedural import profile_procedures
from email_assistant.notifications.schemas import EmailRef, IgnoredDigest, NotifiedNotification, RespondedNotification
from email_assistant.notifications.summary import build, digest_item, render
from email_assistant.profile import load_profile
from email_assistant.prompts import get_prompt


def test_profile_procedures_cover_every_optimizer_target():
    targets = {t["name"] for t in get_prompt("procedural/optimizer").config["targets"]}
    assert targets == set(profile_procedures(load_profile()))


def _state(classification: str, calls: list[dict] | None = None, sample_filter=None):
    sample = next(s for s in load_sample_emails() if (sample_filter or (lambda x: True))(s))
    state = {"email_input": sample.email, "classification": classification, "triage_reasoning": "because"}
    if calls is not None:
        state["messages"] = [AIMessage(content="", tool_calls=[{**c, "id": str(i)} for i, c in enumerate(calls)])]
    return state


TOOLS = {"write_email", "schedule_meeting", "check_calendar_availability", "manage_memory", "search_memory"}


def test_responded_notification_reports_recipient_and_message():
    state = _state("respond", [{"name": "write_email", "args": {"to": "alice.smith@company.com", "subject": "Re: docs", "content": "Hi Alice"}}])
    n = build(state, "fb1", "api-docs-question", TOOLS)
    assert isinstance(n, RespondedNotification) and n.warnings == []
    text = render(n)
    assert "alice.smith@company.com" in text and "Hi Alice" in text and state["email_input"]["author"] in text


def test_reply_to_unknown_address_is_flagged():
    state = _state("respond", [{"name": "write_email", "args": {"to": "someone@else.com", "subject": "x", "content": "y"}}])
    n = build(state, "fb1", "api-docs-question", TOOLS)
    assert any("someone@else.com" in w for w in n.warnings)
    assert "someone@else.com" in render(n)


def test_unknown_tool_and_missing_reply_are_flagged():
    n = build(_state("respond", [{"name": "delete_everything", "args": {}}]), "fb1", "r", TOOLS)
    assert any("delete_everything" in w for w in n.warnings)
    assert any("no reply" in w for w in n.warnings)


def test_reply_recipient_must_be_an_address():
    state = _state("respond", [{"name": "write_email", "args": {"to": "Alice", "subject": "x", "content": "y"}}])
    with pytest.raises(ValidationError):
        build(state, "fb1", "r", TOOLS)


def test_notify_notification_quotes_the_email():
    state = _state("notify", sample_filter=lambda s: s.expected == "notify")
    n = build(state, "fb2", "build-failure", TOOLS)
    assert isinstance(n, NotifiedNotification)
    assert state["email_input"]["subject"] in render(n)


def test_digest_needs_items_and_lists_them():
    with pytest.raises(ValidationError):
        IgnoredDigest(items=[])
    ref = EmailRef(ref="r", sender="News <n@x.com>", to="me", subject="Sale!")
    text = render(IgnoredDigest(items=[digest_item("fb3", ref, "marketing")]))
    assert "1. Sale!" in text and "marketing" in text


def test_user_facing_text_is_stripped_of_markup():
    ref = EmailRef(ref="r", sender="A <a@x.com>", to="me@x.com", subject="Hi")
    n = NotifiedNotification(feedback_id="f", email=ref, reasoning="<b>Looks</b> <!-- x --> important",
                             preview="<!--[if !mso]><!-->\n<!--[if false]><!-->\nReal &lt;i&gt;text&lt;/i&gt;")
    assert n.reasoning == "Looks important" and n.preview == "Real text"
    reply = RespondedNotification(feedback_id="f", email=ref, reasoning="r",
                                  replies=[{"to": "a@x.com", "subject": "Re", "content": "Hi<br>\n<!-- sig -->Bye"}])
    assert reply.replies[0].content == "Hi\nBye"
