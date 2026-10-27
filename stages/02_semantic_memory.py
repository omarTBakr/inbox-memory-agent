"""Stage 02 – adds semantic memory (facts about contacts and projects) in the Postgres store."""

from email_assistant.stage_runner import run

if __name__ == "__main__":
    run("02_semantic_memory")
