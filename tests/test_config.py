import pytest
import yaml

from email_assistant import prompts
from email_assistant.profile import load_profile
from email_assistant.settings import get_settings


def test_profile_loads():
    profile = load_profile()
    assert profile.user.name
    assert profile.triage_rules.respond
    assert profile.agent_instructions


@pytest.mark.parametrize("name", prompts.list_local())
def test_prompt_files_are_consistent(name):
    spec = prompts.load_local(name)
    used = set(prompts._VAR.findall(spec.template))
    assert used == set(spec.variables), f"{name}: template uses {sorted(used)}"
    spec.compile(**{v: "x" for v in spec.variables})


def test_compile_reports_missing_variables():
    spec = prompts.PromptSpec(name="t", template="Hi {{name}}")
    with pytest.raises(KeyError):
        spec.compile()


def test_sample_emails_have_expected_labels():
    s = get_settings()
    emails = yaml.safe_load(s.path(s.sample_emails_path).read_text())["emails"]
    assert {e["expected"] for e in emails} <= {"ignore", "notify", "respond"}
