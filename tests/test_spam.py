from types import SimpleNamespace

from langchain_core.runnables import RunnableLambda

from email_assistant.emails import Email
from email_assistant.graph import baseline
from email_assistant.graph.common import Router, email_prompt
from email_assistant.notifications.schemas import EmailRef, IgnoredDigest
from email_assistant.notifications.summary import build, digest_item, render
from email_assistant.notifications.telegram_bot import digest_keyboard, feedback_keyboard
from email_assistant.profile import load_profile

SPAM = Email(author="Bank <x@bank.example>", to="me@example.com", subject="Verify your account",
             email_thread="Click here", folder="spam")


class _FakeModel:
    def __init__(self, decision: Router):
        self.decision = decision

    def with_structured_output(self, *_, **__):
        return RunnableLambda(lambda _: self.decision)


def _graph(monkeypatch, decision: Router):
    monkeypatch.setattr(baseline, "get_chat_model", lambda: _FakeModel(decision))

    def never(*_):
        raise AssertionError("a Spam email reached the reply agent")

    return baseline.build_email_graph(load_profile(), [], name="t", response_agent=lambda *_: RunnableLambda(never))


def test_spam_is_never_answered(monkeypatch):
    state = _graph(monkeypatch, Router(reasoning="asks me to reply", classification="respond")).invoke({"email_input": SPAM})
    assert state["classification"] == "notify"
    assert "Spam" in state["triage_reasoning"]


def test_inbox_respond_is_unchanged(monkeypatch):
    replied = []
    monkeypatch.setattr(baseline, "get_chat_model", lambda: _FakeModel(Router(reasoning="r", classification="respond")))
    graph = baseline.build_email_graph(load_profile(), [], name="t",
                                       response_agent=lambda *_: RunnableLambda(lambda s: replied.append(1) or {}))
    graph.invoke({"email_input": {**SPAM, "folder": "inbox"}})
    assert replied


def test_triage_input_warns_about_spam_only_for_spam():
    assert "Spam folder" in email_prompt(SPAM)
    assert "Spam folder" not in email_prompt({**SPAM, "folder": "inbox"})
    assert "Spam folder" not in email_prompt({k: v for k, v in SPAM.items() if k != "folder"})


def test_spam_notification_and_digest_are_marked():
    state = {"email_input": SPAM, "classification": "notify", "triage_reasoning": "might be real"}
    note = build(state, "fb1", "gmail:1", set())
    assert note.email.folder == "spam" and "Spam folder" in render(note)
    ref = EmailRef(ref="gmail:2", sender="a@b.c", to="me", subject="Prize", folder="spam")
    assert "(spam)" in render(IgnoredDigest(items=[digest_item("fb2", ref, "junk")]))


def test_not_spam_button_only_for_spam():
    spam_item = {"id": "a", "classification": "notify", "email": dict(SPAM)}
    assert feedback_keyboard(spam_item)[-1][0]["callback_data"] == "fb:a:not_spam"
    assert len(feedback_keyboard({**spam_item, "email": {**SPAM, "folder": "inbox"}})) == 2
    assert feedback_keyboard({**spam_item, "moved_to_inbox": True})[-1][0]["text"] == "✓ in Inbox"
    rows = digest_keyboard([{**spam_item, "classification": "ignore"}, {"id": "b", "classification": "ignore"}])
    assert [r[0]["text"] for r in rows] == ["1 ✓ ignore", "1 📥 Not spam", "2 ✓ ignore"]


def test_not_spam_moves_the_message(monkeypatch):
    from email_assistant.gmail import actions

    calls = []
    messages = SimpleNamespace(modify=lambda **kw: SimpleNamespace(execute=lambda: calls.append(kw)))
    service = SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: messages))
    monkeypatch.setattr(actions, "get_service", lambda: service)
    actions.not_spam("gmail:abc")
    assert calls == [{"userId": "me", "id": "abc", "body": {"removeLabelIds": ["SPAM"], "addLabelIds": ["INBOX"]}}]
