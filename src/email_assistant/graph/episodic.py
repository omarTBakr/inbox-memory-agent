"""Stage 03 graph: semantic memory + episodic memory.

The triage router now sees the most similar past emails (with the label the user
gave them) as few-shot examples, read from (MEMORY_NAMESPACE, <user id>, episodic).
"""

from langgraph.store.base import BaseStore

from email_assistant.graph.baseline import build_email_graph
from email_assistant.memory.episodic import triage_examples
from email_assistant.memory.semantic import semantic_memory_tools
from email_assistant.profile import Profile, load_profile
from email_assistant.tools.email_tools import email_tools


def build_graph(profile: Profile | None = None, store: BaseStore | None = None):
    profile = profile or load_profile()
    tools = email_tools(profile) + semantic_memory_tools(profile)
    return build_email_graph(profile, tools, name="semantic_episodic", store=store, examples=triage_examples)
