"""Pieces shared by every stage graph: state, router schema, prompt rendering."""

from typing import Annotated

from langchain_core.tools import BaseTool
from langgraph.graph import add_messages
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from email_assistant.emails import Classification, Email
from email_assistant.profile import Profile
from email_assistant.prompts import get_prompt


class Router(BaseModel):
    """Analyze the unread email and route it according to its content."""

    reasoning: str = Field(description="Step-by-step reasoning behind the classification.")
    classification: Classification = Field(
        description="'ignore' for irrelevant emails, 'notify' for important information "
        "that doesn't need a response, 'respond' for emails that need a reply",
    )


class State(TypedDict):
    email_input: Email
    classification: NotRequired[Classification]
    triage_reasoning: NotRequired[str]
    examples_used: NotRequired[int]
    notifications: NotRequired[list[dict]]
    feedback_id: NotRequired[str]
    escalation: NotRequired[str]
    messages: Annotated[list, add_messages]


def triage_messages(profile: Profile, email: Email, rules: dict[str, str], examples: str = "") -> list[dict]:
    """`rules` holds triage_ignore / triage_notify / triage_respond (procedures)."""
    u = profile.user
    system = get_prompt("triage/system").compile(
        name=u.name,
        full_name=u.full_name,
        user_profile_background=u.user_profile_background,
        triage_ignore=rules["triage_ignore"],
        triage_notify=rules["triage_notify"],
        triage_respond=rules["triage_respond"],
        examples=examples,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": email_prompt(email)}]


def email_prompt(email: Email) -> str:
    """The email as the triage model sees it, with a warning when it came from Spam."""
    note = get_prompt("triage/spam_note").compile() if email.get("folder") == "spam" else ""
    return get_prompt("triage/user").compile(**email, folder_note=note)


def trajectory(state: State) -> list:
    """What happened in a run, for feedback: the email, the triage decision, then the agent's messages."""
    return [
        {"role": "user", "content": email_prompt(state["email_input"])},
        {"role": "assistant", "content": f"Triage: {state['classification']}. {state['triage_reasoning']}"},
        *state.get("messages", []),
    ]


def format_tools(tools: list[BaseTool]) -> str:
    return "\n".join(f"- {t.name}: {t.description}" for t in tools)


def agent_system_prompt(profile: Profile, tools: list[BaseTool], instructions: str | None = None) -> str:
    u = profile.user
    return get_prompt("response_agent/system").compile(
        name=u.name,
        full_name=u.full_name,
        user_profile_background=u.user_profile_background,
        timezone=u.timezone,
        writing_tone=profile.writing_style.tone,
        signature=profile.writing_style.signature.strip(),
        tools=format_tools(tools),
        instructions=instructions or profile.agent_instructions,
    )


def respond_request(email: Email) -> str:
    """The user message handed to the response agent."""
    return get_prompt("response_agent/user").compile(**email)
