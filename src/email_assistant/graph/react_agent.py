r"""Explicit ReAct reply agent (stage 04): think → act → observe, then draft → review → send.

    START → gather_context → think ─use_tool→ act ─→ think …          (≤ REACT_MAX_STEPS)
                               ├─draft────→ draft_reply → review ─ok→ send → END
                               │                           └─issues→ think (≤ REACT_MAX_REVISIONS), then escalate
                               └─escalate─→ escalate (holding reply) → send → END

Every thought is a structured output (traced in Langfuse); every tool call is recorded as an
AIMessage + ToolMessage, so notifications, feedback and trajectories read it like any agent run.
write_email is not available while thinking: a reply is only sent after review.
"""

import json
import operator
import re
import uuid
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph, add_messages
from pydantic import BaseModel, Field, create_model, model_validator
from typing_extensions import NotRequired, TypedDict

from email_assistant.emails import Email
from email_assistant.graph.common import email_prompt
from email_assistant.llm import get_chat_model, structured_output_method
from email_assistant.memory.store import USER_ID_KEY, namespace
from email_assistant.notifications.schemas import addresses, email_addresses
from email_assistant.profile import Profile
from email_assistant.prompts import get_prompt
from email_assistant.settings import get_settings
from email_assistant.tools.email_tools import WRITE_EMAIL


class Step(TypedDict):
    thought: str
    action: str
    input: dict
    observation: str


class ReactState(TypedDict):
    email_input: Email
    messages: Annotated[list, add_messages]
    scratchpad: Annotated[list[Step], operator.add]
    context: NotRequired[str]
    steps: NotRequired[int]
    revisions: NotRequired[int]
    decision: NotRequired[dict]
    draft: NotRequired[dict]
    issues: NotRequired[list[str]]
    escalation: NotRequired[str]


class Fact(BaseModel):
    fact: str
    source: Literal["email", "memory", "tool"]


class Draft(BaseModel):
    """The reply the agent wants to send, with what it relies on."""

    to: str
    subject: str
    body: str = Field(min_length=1)
    language: str = Field(description="ISO 639-1 code of the reply's language")
    facts: list[Fact] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)


class HoldingReply(BaseModel):
    to: str
    subject: str
    body: str = Field(min_length=1)
    language: str


class Review(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)


NO_TOOL = "none"


def thought_model(tool_names: list[str]) -> type[BaseModel]:
    """Thought schema: reasoning first, then the action. `tool` can only be a real tool or "none".

    Every field is required: with constrained JSON output, optional fields get skipped.
    """

    class _Thought(BaseModel):
        @model_validator(mode="after")
        def _tool_needed(self):
            if self.next == "use_tool" and self.tool == NO_TOOL:
                self.next = "draft"  # no tool named: nothing to run
            return self

    return create_model(
        "Thought",
        __base__=_Thought,
        known=(str, Field(description="What you know so far that matters for the reply")),
        missing=(list[str], Field(description="Information still missing; [] if nothing")),
        reason=(str, Field(description="Why the next action is the right one")),
        next=(Literal["use_tool", "draft", "escalate"], Field(description="The single next action")),
        tool=(Literal[(*tool_names, NO_TOOL)], Field(description=f"Tool to call when next is use_tool, else {NO_TOOL!r}")),
        tool_input=(dict[str, Any], Field(description="Arguments for the tool; {} when not using a tool")),
    )


_PLACEHOLDER = re.compile(r"\[[^\]]{1,40}\]|\bTODO\b|\{\{|\}\}|<[a-zA-Z/][^>]*>")
# the agent's own bookkeeping must never reach the recipient
_INTERNAL = re.compile(r"\(\s*source\s*:|known context|tool result|observation:", re.IGNORECASE)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)\b|\b(\d{1,2}):(\d{2})\b")


def _times(text: str) -> set[str]:
    """Times in a text, normalised to HH:MM (24h)."""
    found = set()
    for h12, m12, ampm, h24, m24 in _TIME.findall(text or ""):
        if ampm:
            hour = int(h12) % 12 + (12 if ampm.lower() == "pm" else 0)
            found.add(f"{hour:02d}:{m12 or '00'}")
        else:
            found.add(f"{int(h24):02d}:{m24}")
    return found


def check_draft(draft: Draft, email: Email, profile: Profile, observations: str) -> list[str]:
    """Deterministic checks a reply must pass before the critic even looks at it."""
    issues = []
    recipients = addresses(draft.to)
    if not recipients:
        issues.append(f"Recipient {draft.to!r} is not an email address.")
    for address in sorted(recipients - email_addresses(email)):
        issues.append(f"Recipient {address} does not appear in the email.")
    signature = [line.strip() for line in profile.writing_style.signature.strip().splitlines() if line.strip()]
    if signature and signature[-1] not in draft.body:
        issues.append(f"The reply must end with the signature ({signature[-1]}).")
    if _PLACEHOLDER.search(draft.body):
        issues.append("The reply contains a placeholder or markup; write the final text.")
    if _INTERNAL.search(draft.body):
        issues.append("The reply mentions internal notes (sources, context, tool results); remove them.")
    unsupported = _times(draft.body) - _times(email["email_thread"]) - _times(observations)
    if unsupported:
        issues.append(f"Times {sorted(unsupported)} were not returned by the calendar or written in the email.")
    if draft.language.lower()[:2] not in [lang.lower()[:2] for lang in profile.user.languages]:
        issues.append(f"Reply language '{draft.language}' is not one of {profile.user.languages}.")
    return issues


def _email_text(email: Email) -> str:
    return email_prompt(email)


def _scratchpad(steps: list[Step]) -> str:
    if not steps:
        return get_prompt("notifications/none").compile()
    return "\n".join(
        f"{i}. Thought: {s['thought']}\n   Action: {s['action']} {json.dumps(s['input'], ensure_ascii=False)}\n"
        f"   Observation: {s['observation']}"
        for i, s in enumerate(steps, start=1)
    )


def _format_tools(tools: list[BaseTool]) -> str:
    return "\n".join(f"- {t.name}({', '.join(t.args)}): {t.description}" for t in tools)


def build_react_agent(profile: Profile, tools: list[BaseTool], procedures):
    s = get_settings()
    llm = get_chat_model()
    method = structured_output_method()
    send_tool = next(t for t in tools if t.name == WRITE_EMAIL)
    loop_tools = {t.name: t for t in tools if t.name != WRITE_EMAIL}
    Thought = thought_model(list(loop_tools))
    thinker = llm.with_structured_output(Thought, method=method)
    drafter = llm.with_structured_output(Draft, method=method)
    critic = llm.with_structured_output(Review, method=method)
    holder = llm.with_structured_output(HoldingReply, method=method)

    def rules(config: RunnableConfig) -> str:
        u, sched, style = profile.user, profile.scheduling, profile.writing_style
        return get_prompt("response_agent/react_rules").compile(
            name=u.name,
            full_name=u.full_name,
            languages=", ".join(u.languages),
            timezone=u.timezone,
            working_days=", ".join(u.working_hours.days),
            working_hours=f"{u.working_hours.start}-{u.working_hours.end}",
            buffer_minutes=sched.buffer_minutes,
            meeting_minutes=sched.default_meeting_minutes,
            no_meetings=", ".join(sched.no_meetings) or get_prompt("notifications/none").compile(),
            tone=style.tone,
            signature=style.signature.strip(),
            escalate_when="\n".join(f"- {topic}" for topic in profile.escalate_when),
            instructions=procedures(config)["agent_instructions"],
        )

    def gather_context(state: ReactState, config: RunnableConfig) -> dict:
        email = state["email_input"]
        ns = namespace(config["configurable"][USER_ID_KEY], s.memory_semantic_collection)
        seen, notes = set(), []
        for query in (email["author"], email["subject"]):
            for item in get_store().search(ns, query=query, limit=s.react_context_memories):
                text = str(item.value.get("content", item.value))
                if text not in seen:
                    seen.add(text)
                    notes.append(f"- {text}")
        return {"context": "\n".join(notes[: s.react_context_memories]) or get_prompt("notifications/none").compile(),
                "steps": 0, "revisions": 0}

    def think(state: ReactState, config: RunnableConfig) -> dict:
        step = state.get("steps", 0) + 1
        prompt = get_prompt("response_agent/react_think").compile(
            rules=rules(config), email=_email_text(state["email_input"]), context=state["context"],
            tools=_format_tools(list(loop_tools.values())), scratchpad=_scratchpad(state["scratchpad"]),
            step=step, max_steps=s.react_max_steps,
        )
        decision = thinker.invoke(prompt)
        if step > s.react_max_steps and decision.next == "use_tool":
            decision.next = "draft"  # out of steps: write with what is known
        return {"decision": decision.model_dump(), "steps": step}

    def act(state: ReactState, config: RunnableConfig) -> dict:
        d = state["decision"]
        call = {"name": d["tool"], "args": d["tool_input"], "id": f"call_{uuid.uuid4().hex[:12]}"}
        try:
            observation, status = str(loop_tools[d["tool"]].invoke(d["tool_input"], config)), "success"
        except Exception as e:  # a failed tool call is an observation the agent can react to
            observation, status = f"ERROR: {type(e).__name__}: {e}", "error"
        return {
            "messages": [AIMessage(content=d["reason"], tool_calls=[call]),
                         ToolMessage(content=observation, tool_call_id=call["id"], name=d["tool"], status=status)],
            "scratchpad": [{"thought": d["reason"], "action": d["tool"], "input": d["tool_input"],
                            "observation": observation}],
        }

    def draft_reply(state: ReactState, config: RunnableConfig) -> dict:
        prompt = get_prompt("response_agent/react_draft").compile(
            rules=rules(config), email=_email_text(state["email_input"]), context=state["context"],
            scratchpad=_scratchpad(state["scratchpad"]),
        )
        return {"draft": drafter.invoke(prompt).model_dump()}

    def review(state: ReactState, config: RunnableConfig) -> dict:
        draft = Draft.model_validate(state["draft"])
        observations = "\n".join(step["observation"] for step in state["scratchpad"])
        issues = check_draft(draft, state["email_input"], profile, observations)
        if not issues:
            verdict = critic.invoke(get_prompt("response_agent/react_review").compile(
                rules=rules(config), email=_email_text(state["email_input"]), context=state["context"],
                scratchpad=_scratchpad(state["scratchpad"]), draft=draft.model_dump_json(indent=2),
            ))
            issues = [] if verdict.ok else (verdict.issues or ["The reviewer rejected the draft."])
        if not issues:
            return {"issues": []}
        return {
            "issues": issues,
            "revisions": state.get("revisions", 0) + 1,
            "scratchpad": [{"thought": "Review of the draft", "action": "review", "input": {},
                            "observation": "Issues to fix: " + " ".join(issues)}],
        }

    def escalate(state: ReactState, config: RunnableConfig) -> dict:
        d = state.get("decision") or {}
        # chosen while thinking, or reached because the draft kept failing review
        reason = d["reason"] if d.get("next") == "escalate" else "; ".join(state.get("issues") or [])
        reply = holder.invoke(get_prompt("response_agent/react_holding").compile(
            rules=rules(config), email=_email_text(state["email_input"]), reason=reason,
        ))
        return {"draft": reply.model_dump(), "escalation": reason}

    def send(state: ReactState, config: RunnableConfig) -> dict:
        draft = state["draft"]
        args = {"to": draft["to"], "subject": draft["subject"], "content": draft["body"]}
        call = {"name": WRITE_EMAIL, "args": args, "id": f"call_{uuid.uuid4().hex[:12]}"}
        result = str(send_tool.invoke(args, config))
        return {"messages": [AIMessage(content="", tool_calls=[call]),
                             ToolMessage(content=result, tool_call_id=call["id"], name=WRITE_EMAIL)]}

    def after_think(state: ReactState) -> str:
        return {"use_tool": "act", "draft": "draft_reply", "escalate": "escalate"}[state["decision"]["next"]]

    def after_review(state: ReactState) -> str:
        if not state["issues"]:
            return "send"
        return "think" if state["revisions"] <= s.react_max_revisions else "escalate"

    graph = StateGraph(ReactState)
    graph.add_node("gather_context", gather_context)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("review", review)
    graph.add_node("escalate", escalate)
    graph.add_node("send", send)
    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "think")
    graph.add_conditional_edges("think", after_think, ["act", "draft_reply", "escalate"])
    graph.add_edge("act", "think")
    graph.add_edge("draft_reply", "review")
    graph.add_conditional_edges("review", after_review, ["send", "think", "escalate"])
    graph.add_edge("escalate", "send")
    graph.add_edge("send", END)
    return graph.compile(name="response_agent")
