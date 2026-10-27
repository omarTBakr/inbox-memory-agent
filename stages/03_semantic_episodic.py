"""Stage 03 – adds episodic memory: past emails labelled by the user become few-shot triage examples.

Record a label with `make feedback EMAIL=<sample id> LABEL=ignore|notify|respond`."""

from email_assistant.stage_runner import run

if __name__ == "__main__":
    run("03_semantic_episodic")
