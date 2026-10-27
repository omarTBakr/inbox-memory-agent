"""Stage 02 graph: baseline + semantic memory.

Same shape as stage 01; the response agent also gets manage_memory / search_memory,
which read and write facts in the Postgres store under
(MEMORY_NAMESPACE, <user id>, "semantic").
"""

from langgraph.store.base import BaseStore

from email_assistant.graph.baseline import build_email_graph
from email_assistant.memory.semantic import semantic_memory_tools
from email_assistant.profile import Profile, load_profile
from email_assistant.tools.email_tools import email_tools


def build_graph(profile: Profile | None = None, store: BaseStore | None = None):
    profile = profile or load_profile()
    tools = email_tools(profile) + semantic_memory_tools(profile)
    return build_email_graph(profile, tools, name="semantic", store=store)
