from email_assistant.notifications.telegram_bot import digest_keyboard, feedback_keyboard


def _texts(rows):
    return [[b["text"] for b in row] for row in rows]


def test_current_decision_is_ticked_and_actions_follow():
    rows = feedback_keyboard({"id": "abc", "classification": "notify"})
    assert _texts(rows)[0] == ["ignore", "✓ notify", "respond"]
    assert [b["callback_data"] for b in rows[0]] == ["fb:abc:label_ignore", "fb:abc:label_notify", "fb:abc:label_respond"]
    assert _texts(rows)[1] == ["👍", "👎", "✍️ feedback"]


def test_tick_follows_correction_and_rating():
    rows = feedback_keyboard({"id": "abc", "classification": "ignore", "corrected_label": "notify", "rating": "down"})
    assert _texts(rows) == [["ignore", "✓ notify", "respond"], ["👍", "👎 ✓", "✍️ feedback"]]


def test_digest_has_a_numbered_row_per_email():
    rows = digest_keyboard([{"id": "a", "classification": "ignore"}, {"id": "b", "classification": "ignore"}])
    assert _texts(rows) == [["1 ✓ ignore", "1 notify", "1 respond", "1 ✍️"], ["2 ✓ ignore", "2 notify", "2 respond", "2 ✍️"]]
    assert all(len(b["callback_data"].encode()) <= 64 for row in rows for b in row)
