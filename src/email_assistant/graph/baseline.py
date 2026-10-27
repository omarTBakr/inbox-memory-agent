r"""Stage 01 graph: triage router -> response agent. No long-term memory.

    START -> triage_router --respond--> response_agent -> END
                          \--ignore / notify--> END

`build_email_graph` is the shape every stage reuses; later stages pass more tools,
a store, few-shot triage examples, live procedures, and the notify_user node.
"""

from collections.abc import Callable
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Command

from email_assistant.emails import Email
from email_assistant.graph.common import Router, State, agent_system_prompt, respond_request, triage_messages
from email_assistant.llm import get_chat_model, structured_output_method
from email_assistant.memory.procedural import Procedures, profile_procedures
from email_assistant.profile import Profile, load_profile
from email_assistant.prompts import get_prompt
from email_assistant.tools.email_tools import email_tools

# (email, config) -> formatted few-shot examples for the triage prompt
ExamplesFn = Callable[[Email, RunnableConfig], list[str]]
# config -> triage rules + agent instructions in force for this run
ProceduresFn = Callable[[RunnableConfig], Procedures]
# (profile, tools, procedures) -> compiled reply agent used for "respond"
AgentFactory = Callable[[Profile, list[BaseTool], ProceduresFn], Any]


def build_email_graph(
    profile: Profile,
    tools: list[BaseTool],
    *,
    name: str,
    store: BaseStore | None = None,
    examples: ExamplesFn | None = None,
    procedures: ProceduresFn | None = None,
    notify: Callable[[State, RunnableConfig], dict] | None = None,
    response_agent: AgentFactory | None = None,
):
    procedures = procedures or (lambda config: profile_procedures(profile))
    llm = get_chat_model()
    router = llm.with_structured_output(Router, method=structured_output_method())

    if response_agent:
        agent = response_agent(profile, tools, procedures)
    else:
        @dynamic_prompt
        def system_prompt(request: ModelRequest) -> str:
            # rendered per call so procedural-memory updates apply without a rebuild
            return agent_system_prompt(profile, tools, procedures(get_config())["agent_instructions"])

        agent = create_agent(llm, tools=tools, middleware=[system_prompt], name="response_agent")

    def triage_router(state: State, config: RunnableConfig) -> Command[Literal["response_agent", "notify_user", "__end__"]]:
        shots = examples(state["email_input"], config) if examples else []
        messages = triage_messages(profile, state["email_input"], procedures(config), "\n\n".join(shots))
        result: Router = router.invoke(messages)
        if result.classification == "respond" and state["email_input"].get("folder") == "spam":
            # enforced here, not only in the prompt: Spam may be phishing, so it is never answered
            result = Router(classification="notify",
                            reasoning=f"{result.reasoning} {get_prompt('triage/spam_guard').compile()}")
        update = {
            "classification": result.classification,
            "triage_reasoning": result.reasoning,
            "examples_used": len(shots),
        }
        if result.classification == "respond":
            update["messages"] = [{"role": "user", "content": respond_request(state["email_input"])}]
            return Command(goto="response_agent", update=update)
        if notify:  # notify_user decides: push, queue for the ignored digest, or nothing
            return Command(goto="notify_user", update=update)
        return Command(goto=END, update=update)

    destinations = ("response_agent", "notify_user", END) if notify else ("response_agent", END)
    graph = StateGraph(State)
    graph.add_node("triage_router", triage_router, destinations=destinations)
    graph.add_node("response_agent", agent)
    graph.add_edge(START, "triage_router")
    if notify:
        graph.add_node("notify_user", notify)
        graph.add_edge("response_agent", "notify_user")
        graph.add_edge("notify_user", END)
    return graph.compile(name=name, store=store)


def build_graph(profile: Profile | None = None, store: BaseStore | None = None):
    profile = profile or load_profile()
    return build_email_graph(profile, email_tools(profile), name="baseline", store=store)
