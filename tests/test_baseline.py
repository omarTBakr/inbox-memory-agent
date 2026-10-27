from email_assistant.emails import load_sample_emails
from email_assistant.graph.common import agent_system_prompt, triage_messages
from email_assistant.memory.procedural import profile_procedures
from email_assistant.memory.semantic import semantic_memory_tools
from email_assistant.profile import load_profile
from email_assistant.stages import STAGES
from email_assistant.tools.email_tools import _free_slots, email_tools


def test_triage_messages_render_for_every_sample():
    profile = load_profile()
    for sample in load_sample_emails():
        system, user = triage_messages(profile, sample.email, profile_procedures(profile))
        assert profile.triage_rules.respond in system["content"]
        assert sample.email["subject"] in user["content"]


def test_agent_prompt_lists_the_given_tools():
    profile = load_profile()
    tools = email_tools(profile)
    prompt = agent_system_prompt(profile, tools)
    assert all(t.name in prompt for t in tools)
    assert "manage_memory" not in prompt
    with_memory = agent_system_prompt(profile, tools + semantic_memory_tools(profile))
    assert "manage_memory" in with_memory and "search_memory" in with_memory


def test_free_slots_follow_profile_settings():
    profile = load_profile().model_copy(deep=True)
    profile.user.working_hours.start, profile.user.working_hours.end = "09:00", "11:00"
    profile.scheduling.default_meeting_minutes, profile.scheduling.buffer_minutes = 30, 10
    assert _free_slots(profile) == ["09:00", "09:40", "10:20"]


def test_every_stage_graph_builds():
    for stage in STAGES.values():
        assert stage.build_graph().get_graph() is not None
