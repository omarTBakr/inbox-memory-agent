r"""Stage 04 graph: semantic + episodic + procedural memory, and push notifications.

    START -> triage_router --respond--> response_agent (ReAct, graph/react_agent.py) -> notify_user -> END
                          \--notify / ignore-------------------^

Triage rules and agent instructions come from procedural memory (rewritten by
`make teach` or 👍/👎 feedback). notify_user records every handled email for feedback,
pushes a validated notification with 👍/👎 to Telegram (respond / notify, per notify_on),
and queues ignored emails for the daily digest.
"""

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from email_assistant import config_store
from email_assistant.feedback import store as feedback_store
from email_assistant.graph.baseline import build_email_graph
from email_assistant.graph.common import State, trajectory
from email_assistant.graph.react_agent import build_react_agent
from email_assistant.memory import procedural
from email_assistant.memory.episodic import triage_examples
from email_assistant.memory.semantic import semantic_memory_tools
from email_assistant.notifications.push import push
from email_assistant.notifications.summary import build, render
from email_assistant.notifications.telegram_bot import feedback_keyboard
from email_assistant.profile import Profile, load_profile
from email_assistant.tools.email_tools import email_tools
from email_assistant.tracing import score


def build_graph(profile: Profile | None = None, store: BaseStore | None = None):
    profile = profile or load_profile()
    tools = email_tools(profile) + semantic_memory_tools(profile)
    tool_names = {t.name for t in tools}

    def notify_user(state: State, config: RunnableConfig) -> dict:
        """Record the run for feedback, then push a validated notification with 👍/👎."""
        cfg = config_store.section("notifications")
        run = config.get("configurable", {})
        classification = state["classification"]
        if classification == "ignore" and not cfg.ignored_digest:
            return {"notifications": []}
        item_id = feedback_store.new_id()
        score(run.get("trace_id"), "triage_classification", classification, data_type="CATEGORICAL")
        record = {
            "stage": run.get("stage", "04_semantic_episodic_procedural"),
            "email_ref": run.get("email_ref", ""),
            "email": dict(state["email_input"]),
            "classification": classification,
            "reasoning": state["triage_reasoning"],
            "trajectory": procedural.compact_trajectory(trajectory(state)),
            "trace_id": run.get("trace_id"),
            "mlflow_run_id": run.get("mlflow_run_id"),
        }
        if classification == "ignore":  # waits for the ignored-email digest
            feedback_store.create(item_id, **record)
            return {"notifications": [], "feedback_id": item_id}
        notification = build(state, item_id, record["email_ref"], tool_names)
        score(run.get("trace_id"), "notification_warnings", len(notification.warnings),
              comment="; ".join(notification.warnings) or None)
        feedback_store.create(item_id, **record, notification=notification.model_dump(mode="json"))
        if classification not in cfg.notify_on:
            return {"notifications": [], "feedback_id": item_id}
        text = render(notification)
        results = push(text, cfg, keyboard=feedback_keyboard({"id": item_id, "classification": classification, "email": record["email"]}))
        bot_message = next((r["message_id"] for r in results if r["channel"] == "telegram" and r.get("message_id")), None)
        if bot_message:
            feedback_store.update(item_id, telegram_message_id=bot_message)
        return {"notifications": [{"text": text, **r} for r in results], "feedback_id": item_id}

    return build_email_graph(
        profile,
        tools,
        name="semantic_episodic_procedural",
        store=store,
        examples=triage_examples,
        procedures=procedural.from_store(profile),
        notify=notify_user,
        response_agent=build_react_agent,
    )
