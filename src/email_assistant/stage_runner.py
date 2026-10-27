"""Shared stage loop: run the sample emails through a graph, print, log to MLflow / Langfuse."""

import sys
from contextlib import nullcontext

from email_assistant.emails import SampleEmail, load_sample_emails
from email_assistant.memory.store import USER_ID_KEY, get_store
from email_assistant.profile import Profile, load_profile
from email_assistant.stages import STAGES
from email_assistant.tracing import callbacks, flush, log_results, new_trace_id, stage_run


def _format_call(call: dict) -> str:
    return f"{call['name']}({', '.join(f'{k}={v!r}' for k, v in call['args'].items())})"


def run_stage(stage: str, graph, profile: Profile, samples: list[SampleEmail] | None = None) -> list[dict]:
    samples = samples or load_sample_emails()
    rows = []
    with stage_run(stage, n_emails=len(samples), user_id=profile.user.id) as mlflow_run:
        for sample in samples:
            trace_id = new_trace_id()
            config = {
                "callbacks": callbacks(trace_id),
                "run_name": f"{stage}:{sample.id}",
                "metadata": {"langfuse_tags": [stage], "email_id": sample.id},
                "configurable": {
                    USER_ID_KEY: profile.user.id,
                    "stage": stage,
                    "email_ref": sample.id,
                    "trace_id": trace_id,
                    "mlflow_run_id": mlflow_run.info.run_id if mlflow_run else None,
                },
            }
            state = graph.invoke({"email_input": sample.email}, config=config)
            tool_calls = [
                _format_call(call)
                for message in state.get("messages", [])
                for call in getattr(message, "tool_calls", [])
            ]
            tool_errors = [
                f"{m.name}: {str(m.content)[:200]}"
                for m in state.get("messages", [])
                if getattr(m, "type", None) == "tool" and getattr(m, "status", None) == "error"
            ]
            rows.append({
                "email_id": sample.id,
                "expected": sample.expected,
                "classification": state["classification"],
                "correct": state["classification"] == sample.expected if sample.expected else None,
                "sender": sample.email["author"],
                "subject": sample.email["subject"],
                "examples_used": state.get("examples_used", 0),
                "reasoning": state["triage_reasoning"],
                "tool_calls": "\n".join(tool_calls),
                "tool_errors": "\n".join(tool_errors),
                "feedback_id": state.get("feedback_id"),
                "escalation": state.get("escalation"),
                "notifications": "\n".join(
                    f"{n['channel']}: {'ok' if n['ok'] else 'FAILED'} ({n['detail']})" for n in state.get("notifications", [])
                ),
            })
            mark = {True: "ok ", False: "BAD", None: " - "}[rows[-1]["correct"]]
            shots = f", {rows[-1]['examples_used']} examples" if rows[-1]["examples_used"] else ""
            expected = f"expected {sample.expected}" if sample.expected else sample.email["subject"][:60]
            print(f"[{mark}] {sample.id}: {state['classification']} ({expected}{shots})")
            for call in tool_calls:
                print(f"       -> {call}")
            for error in tool_errors:
                print(f"       !! {error}")
            if state.get("escalation"):
                print(f"       ?? escalated: {state['escalation']}")
            if notes := state.get("notifications"):
                print("       >> push " + ", ".join(f"{n['channel']}:{'ok' if n['ok'] else 'FAILED'} ({n['detail']})" for n in notes))
                print("          " + notes[0]["text"].replace("\n", "\n          "))

        n_errors = sum(len(r["tool_errors"].splitlines()) for r in rows)
        metrics = {"tool_errors": n_errors}
        labelled = [r for r in rows if r["correct"] is not None]
        if labelled:
            metrics["triage_accuracy"] = sum(r["correct"] for r in labelled) / len(labelled)
            print(f"Triage accuracy: {metrics['triage_accuracy']:.0%}, tool errors: {n_errors}")
        else:
            print(f"{len(rows)} emails processed, tool errors: {n_errors}")
        log_results(rows, metrics)
    flush()
    return rows


def run(stage_id: str, samples: list[SampleEmail] | None = None) -> list[dict]:
    """Build the stage's graph (with the Postgres store if it needs one) and run the emails."""
    stage = STAGES[stage_id]
    profile = load_profile()
    with get_store() if stage.uses_store else nullcontext() as store:
        return run_stage(stage.id, stage.build_graph(profile, store), profile, samples)


if __name__ == "__main__":
    run(sys.argv[1])
