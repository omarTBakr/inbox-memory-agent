from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from email_assistant.gmail import watcher

CFG = SimpleNamespace(query="is:unread in:inbox", spam_query="in:spam is:unread", include_spam=True, max_per_tick=5)


def _call(result):
    return SimpleNamespace(execute=result if callable(result) else (lambda: result))


class FakeGmail:
    """history: {label: [message ids added]}; matching: ids returned by searches."""

    def __init__(self, history, matching, history_id=200, expired=False):
        self.added, self.matching, self.history_id, self.expired = history, matching, history_id, expired
        self.queries = []

    def users(self):
        return self

    def getProfile(self, userId):
        return _call({"historyId": str(self.history_id)})

    def history_(self, userId, startHistoryId, historyTypes, labelId, pageToken):
        if self.expired:
            def boom():
                raise HttpError(SimpleNamespace(status=404, reason="expired"), b"")
            return _call(boom)
        added = [{"messagesAdded": [{"message": {"id": i, "labelIds": [labelId]}}]} for i in self.added.get(labelId, [])]
        return _call({"history": added, "historyId": str(self.history_id)})

    def history(self):  # the Gmail client shape: users().history().list(...)
        return SimpleNamespace(list=self.history_)

    def messages(self):
        def list_(userId, q, maxResults, includeSpamTrash):
            self.queries.append((q, includeSpamTrash))
            return _call({"messages": [{"id": i} for i in self.matching]})
        return SimpleNamespace(list=list_)


@pytest.fixture
def state(monkeypatch):
    saved = {}
    monkeypatch.setattr(watcher, "_history_id", lambda: saved.get("h"))
    monkeypatch.setattr(watcher, "_save_history_id", lambda h: saved.__setitem__("h", h))
    return saved


def test_first_check_only_records_where_history_is(state):
    gmail = FakeGmail({"INBOX": ["a"]}, ["a"])
    assert watcher.find_new(gmail, CFG) == {}
    assert state["h"] == 200


def test_new_mail_must_match_the_search_and_keeps_its_folder(state):
    state["h"] = 100
    gmail = FakeGmail({"INBOX": ["a", "read-already"], "SPAM": ["s"]}, ["a", "s"], history_id=150)
    assert watcher.find_new(gmail, CFG) == {"a": "inbox", "s": "spam"}
    assert state["h"] == 150
    assert ("in:spam is:unread", True) in gmail.queries


def test_spam_is_skipped_unless_included(state):
    state["h"] = 100
    gmail = FakeGmail({"INBOX": ["a"], "SPAM": ["s"]}, ["a", "s"])
    assert watcher.find_new(gmail, SimpleNamespace(**{**vars(CFG), "include_spam": False})) == {"a": "inbox"}


def test_expired_history_catches_up_with_a_search(state):
    state["h"] = 1
    gmail = FakeGmail({}, ["x"], history_id=900, expired=True)
    assert set(watcher.find_new(gmail, CFG)) == {"x"}
    assert state["h"] == 900
    assert all("newer_than" in q for q, _ in gmail.queries)


def test_one_failing_email_does_not_stop_the_others(monkeypatch):
    from email_assistant import stage_runner
    from email_assistant.emails import Email, SampleEmail
    from email_assistant.gmail import messages

    marks = {}
    monkeypatch.setattr(watcher, "mark", lambda i, status, **f: marks.__setitem__(i, (status, f)))
    monkeypatch.setattr(messages, "fetch", lambda ids, gmail=None: [
        SampleEmail(id=f"gmail:{ids[0]}", expected=None, email=Email(author="a", to="b", subject=ids[0], email_thread=""))])

    def run(stage, samples):
        if samples[0].email["subject"] == "bad":
            raise RuntimeError("model down")
        return [{"email_id": samples[0].id, "classification": "notify", "feedback_id": "fb"}]

    monkeypatch.setattr(stage_runner, "run", run)
    rows = watcher.process(["bad", "good"])
    assert len(rows) == 1
    assert marks["bad"][0] == "error" and "model down" in marks["bad"][1]["error"]
    assert marks["good"] == ("done", {"feedback_id": "fb", "classification": "notify", "subject": "good", "error": None})
