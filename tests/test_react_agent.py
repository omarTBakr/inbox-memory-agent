import pytest
from pydantic import ValidationError

from email_assistant.emails import load_sample_emails
from email_assistant.graph.react_agent import Draft, _times, check_draft, thought_model
from email_assistant.profile import load_profile

EMAIL = next(s for s in load_sample_emails() if s.id == "meeting-request").email
PROFILE = load_profile()
SIGNATURE = PROFILE.writing_style.signature.strip().splitlines()[-1]


def _draft(**overrides):
    base = {"to": "tom.jones@company.com", "subject": "Re: sync", "language": PROFILE.user.languages[0],
            "body": f"Hi Tom,\n\nTuesday works.\n\n{SIGNATURE}"}
    return Draft(**(base | overrides))


def test_clean_draft_passes():
    assert check_draft(_draft(), EMAIL, PROFILE, observations="") == []


def test_unknown_recipient_and_non_address_are_caught():
    assert any("does not appear" in i for i in check_draft(_draft(to="ceo@else.com"), EMAIL, PROFILE, ""))
    assert any("not an email address" in i for i in check_draft(_draft(to="Tom"), EMAIL, PROFILE, ""))


def test_missing_signature_and_placeholders_are_caught():
    issues = check_draft(_draft(body="Hi Tom, see [LINK] and TODO."), EMAIL, PROFILE, "")
    assert any("signature" in i for i in issues) and any("placeholder" in i for i in issues)


def test_times_must_come_from_calendar_or_email():
    body = f"Hi Tom, how about 3:30 pm on Tuesday?\n\n{SIGNATURE}"
    assert any("Times" in i for i in check_draft(_draft(body=body), EMAIL, PROFILE, observations=""))
    assert check_draft(_draft(body=body), EMAIL, PROFILE, observations="Available start times: 15:30") == []
    assert _times("2:00 PM, 14:30 and 9am") == {"14:00", "14:30", "09:00"}


def test_reply_language_must_be_allowed():
    assert any("language" in i for i in check_draft(_draft(language="xx"), EMAIL, PROFILE, ""))


def test_thought_only_accepts_real_tools():
    Thought = thought_model(["search_memory", "check_calendar_availability"])
    base = {"known": "k", "missing": [], "reason": "r", "tool_input": {}}
    ok = Thought(**base | {"next": "use_tool", "tool": "search_memory", "tool_input": {"query": "Tom"}})
    assert ok.tool == "search_memory"
    with pytest.raises(ValidationError):
        Thought(**base | {"next": "use_tool", "tool": "write_email"})
    assert Thought(**base | {"next": "use_tool", "tool": "none"}).next == "draft"
    assert set(Thought.model_json_schema()["required"]) >= {"next", "tool", "tool_input"}


def test_internal_notes_must_not_reach_the_recipient():
    body = f"Hi Tom, Tuesday works (Source: Known context).\n\n{SIGNATURE}"
    assert any("internal notes" in i for i in check_draft(_draft(body=body), EMAIL, PROFILE, ""))


def test_schedule_meeting_books_only_free_slots():
    from email_assistant.tools.email_tools import _free_slots, email_tools

    schedule = next(t for t in email_tools(PROFILE) if t.name == "schedule_meeting")
    free = _free_slots(PROFILE)[0]
    args = {"attendees": ["tom.jones@company.com"], "subject": "Sync", "duration_minutes": 30, "preferred_day": "Tuesday"}
    assert schedule.invoke(args | {"start_time": free}).startswith(f"Booked 'Sync' on Tuesday {free}-")
    assert schedule.invoke(args | {"start_time": "03:00"}).startswith("Not booked")
