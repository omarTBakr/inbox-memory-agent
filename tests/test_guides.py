from email_assistant import guides
from email_assistant.api.routers.setup import STEPS
from email_assistant.settings import get_settings


def test_every_setup_step_has_a_guide():
    assert set(STEPS) == set(guides.load()["steps"])


def test_setup_guide_doc_is_up_to_date():
    s = get_settings()
    assert s.path(s.setup_guide_doc).read_text() == guides.to_markdown(), "run `make docs`"
