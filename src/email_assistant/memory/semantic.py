"""Semantic memory: facts about people, projects and preferences, managed by the agent itself."""

from langchain_core.tools import BaseTool
from langmem import create_manage_memory_tool, create_search_memory_tool

from email_assistant.memory.store import USER_ID_KEY, namespace
from email_assistant.profile import Profile
from email_assistant.prompts import get_prompt
from email_assistant.settings import get_settings


def semantic_memory_tools(profile: Profile) -> list[BaseTool]:
    # langmem fills the {placeholder} from config["configurable"] at call time
    ns = namespace(f"{{{USER_ID_KEY}}}", get_settings().memory_semantic_collection)
    name = profile.user.name
    return [
        create_manage_memory_tool(
            namespace=ns,
            instructions=get_prompt("memory/semantic_extraction").compile(name=name),
        ),
        create_search_memory_tool(
            namespace=ns,
            instructions=get_prompt("memory/semantic_search").compile(name=name),
        ),
    ]
