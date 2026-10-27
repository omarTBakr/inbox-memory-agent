"""Stage 04 – adds procedural memory (feedback rewrites triage rules and agent instructions)
and push notifications of what the assistant did (Telegram).

Teach it with `make teach EMAIL=<sample id> FEEDBACK="..."`.
"""

from email_assistant.stage_runner import run

if __name__ == "__main__":
    run("04_semantic_episodic_procedural")
