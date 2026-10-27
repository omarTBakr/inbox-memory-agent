"""Command line entry point (`email-assistant ...`, used by the Makefile)."""

import argparse
import json
import logging
import sys
from typing import get_args

from email_assistant.emails import Classification
from email_assistant.settings import get_settings


def _masked_settings() -> dict:
    return json.loads(get_settings().model_dump_json())  # SecretStr dumps as "**********"


def cmd_check_env(_: argparse.Namespace) -> int:
    problems = get_settings().problems()
    for p in problems:
        print(f"  x {p}")
    print("Environment OK" if not problems else f"{len(problems)} problem(s) in .env")
    return 1 if problems else 0


def cmd_profile(_: argparse.Namespace) -> int:
    from email_assistant.profile import load_profile

    print("# Profile")
    print(json.dumps(load_profile().model_dump(), indent=2))
    print("\n# Settings")
    print(json.dumps(_masked_settings(), indent=2, default=str))
    return 0


def cmd_db_init(_: argparse.Namespace) -> int:
    from email_assistant.memory.store import setup_database

    setup_database()
    print("Store and checkpointer tables are ready")
    return 0


def cmd_prompts(args: argparse.Namespace) -> int:
    from email_assistant import prompts

    if args.action == "history":
        if not args.name:
            print("usage: prompts history <name>   e.g. triage/system", file=sys.stderr)
            return 2
        for row in prompts.history(args.name):
            labels = ",".join(row["labels"]) or "-"
            print(f"v{row['version']:<4} {row['digest']}  [{labels}]  {row['commit_message'] or ''}")
        return 0
    names = [args.name] if args.name else prompts.list_local()
    action = prompts.push if args.action == "push" else prompts.pull
    for name in names:
        print(action(name))
    return 0


def _all_items(store, prefix: tuple[str, ...]) -> list:
    page, items = get_settings().memory_page_size, []
    while batch := store.search(prefix, limit=page, offset=len(items)):
        items += batch
    return items


def cmd_memory(args: argparse.Namespace) -> int:
    from email_assistant.memory.store import get_store, namespace
    from email_assistant.profile import load_profile

    prefix = namespace(load_profile().user.id, *([args.kind] if args.kind else []))
    with get_store() as store:
        items = _all_items(store, prefix)
        if args.action == "clear":
            for item in items:
                store.delete(item.namespace, item.key)
            print(f"Deleted {len(items)} memories under {'/'.join(prefix)}")
            return 0
        for item in items:
            print(f"[{'/'.join(item.namespace[2:])}] {item.key}  {item.updated_at:%Y-%m-%d %H:%M}")
            print(f"    {item.value}")
        print(f"{len(items)} memories under {'/'.join(prefix)}")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    """Record the correct triage label for a sample email as an episodic example."""
    from email_assistant.emails import load_sample_emails
    from email_assistant.memory.episodic import record_example
    from email_assistant.memory.store import get_store
    from email_assistant.profile import load_profile

    samples = {s.id: s for s in load_sample_emails()}
    if args.email_id not in samples:
        print(f"Unknown email id {args.email_id!r}; choose from: {', '.join(samples)}", file=sys.stderr)
        return 2
    with get_store() as store:
        key = record_example(store, load_profile().user.id, samples[args.email_id].email, args.label, source="cli")
    print(f"Recorded {args.email_id} -> {args.label} (episodic key {key})")
    return 0


def _sample(email_id: str):
    from email_assistant.emails import load_sample_emails

    samples = {s.id: s for s in load_sample_emails()}
    if email_id not in samples:
        raise SystemExit(f"Unknown email id {email_id!r}; choose from: {', '.join(samples)}")
    return samples[email_id]


def cmd_teach(args: argparse.Namespace) -> int:
    """Run an email through stage 04, then let the feedback rewrite procedural memory."""
    from email_assistant.memory import procedural
    from email_assistant.memory.store import USER_ID_KEY, get_store
    from email_assistant.profile import load_profile
    from email_assistant.stages import STAGES
    from email_assistant.tracing import callbacks, flush

    sample, profile = _sample(args.email_id), load_profile()
    stage = STAGES[args.stage]
    with get_store() as store:
        graph = stage.build_graph(profile, store)
        config = {"callbacks": callbacks(), "configurable": {USER_ID_KEY: profile.user.id},
                  "run_name": f"teach:{sample.id}"}
        state = graph.invoke({"email_input": sample.email}, config=config)
        print(f"Run: {sample.id} -> {state['classification']}")
        trajectory = [
            {"role": "user", "content": stage_input(sample.email)},
            {"role": "assistant", "content": f"Triage: {state['classification']}. {state['triage_reasoning']}"},
            *state.get("messages", []),
        ]
        changes = procedural.optimize(store, profile.user.id, profile, trajectory, args.feedback)
    flush()
    for c in changes:
        print(f"\n{c['name']} -> v{c['version']}\n  before: {c['before']}\n  after:  {c['after']}")
    print(f"\n{len(changes)} procedure(s) updated" if changes else "No procedure changed")
    return 0


def stage_input(email) -> str:
    from email_assistant.graph.common import email_prompt

    return email_prompt(email)


def cmd_procedures(_: argparse.Namespace) -> int:
    from email_assistant.memory import procedural
    from email_assistant.memory.store import get_store
    from email_assistant.profile import load_profile

    profile = load_profile()
    with get_store() as store:
        ns = procedural.procedural_namespace(profile.user.id)
        for name, value in procedural.load(store, profile.user.id, profile).items():
            item = store.get(ns, name)
            origin = f"v{item.value['version']} ({item.value['updated_at'][:16]})" if item else "profile"
            print(f"{name} [{origin}]\n  {value}")
    return 0


def cmd_notify_test(_: argparse.Namespace) -> int:
    from email_assistant.notifications.push import push
    from email_assistant.profile import load_profile
    from email_assistant.prompts import get_prompt

    profile = load_profile()
    for r in push(get_prompt("notifications/test").compile(name=profile.user.name), profile.notifications):
        print(f"{r['channel']}: {'ok' if r['ok'] else 'FAILED'} ({r['detail']})")
    return 0


def cmd_telegram_chat_id(_: argparse.Namespace) -> int:
    from email_assistant.notifications.push import telegram_chat_ids

    chats = telegram_chat_ids()
    for c in chats:
        print(f"chat_id={c['chat_id']}  ({c['name']})")
    if not chats:
        print("No chats yet: open your bot in Telegram, send /start, then run this again")
    return 0


def cmd_bot(_: argparse.Namespace) -> int:
    """Run the Telegram feedback listener without the API (don't run both: one poller per bot)."""
    import time

    from email_assistant.notifications.telegram_bot import listener

    listener.start()
    print("Listening for Telegram feedback; Ctrl+C to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        listener.stop()
    return 0


def cmd_digest(_: argparse.Namespace) -> int:
    from email_assistant.feedback.digest import send_digest

    result = send_digest()
    for m in result.get("messages", []):
        print(("SENT\n" if m["sent"] else "NOT SENT (dry run or no telegram channel)\n") + m["text"] + "\n")
    print(f"{result.get('items', 0)} ignored email(s) pending")
    return 0


def cmd_langfuse_models(_: argparse.Namespace) -> int:
    from email_assistant.tracing import sync_model_prices

    for line in sync_model_prices():
        print(line)
    return 0


def cmd_docs(_: argparse.Namespace) -> int:
    from email_assistant.guides import write_markdown

    print(f"Wrote {write_markdown()}")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    from email_assistant.graph.visualize import STAGES, render

    for stage in [args.stage] if args.stage else STAGES:
        for path in render(stage):
            print(f"{stage}: {path}")
    return 0


def cmd_gmail_auth(_: argparse.Namespace) -> int:
    from email_assistant.gmail.client import authorize, connection_test

    authorize()
    print(f"Gmail connected: {connection_test()['email']}")
    return 0


def cmd_config_import(_: argparse.Namespace) -> int:
    """Copy config/user_profile.yml into the UI config store (profile + notifications)."""
    from email_assistant import config_store

    for section in ("profile", "notifications"):
        print(f"{section}: saved v{config_store.save(section, config_store.yaml_section(section))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=get_settings().log_level, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="email-assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-env").set_defaults(func=cmd_check_env)
    sub.add_parser("profile").set_defaults(func=cmd_profile)
    sub.add_parser("db-init").set_defaults(func=cmd_db_init)
    sub.add_parser("gmail-auth").set_defaults(func=cmd_gmail_auth)
    sub.add_parser("config-import").set_defaults(func=cmd_config_import)
    m = sub.add_parser("memory")
    m.add_argument("action", choices=["list", "clear"])
    m.add_argument("kind", nargs="?", help="semantic | episodic | procedural (default: all)")
    m.set_defaults(func=cmd_memory)
    f = sub.add_parser("feedback")
    f.add_argument("email_id", help="id from SAMPLE_EMAILS_PATH")
    f.add_argument("label", choices=get_args(Classification))
    f.set_defaults(func=cmd_feedback)
    t = sub.add_parser("teach")
    t.add_argument("email_id", help="id from SAMPLE_EMAILS_PATH")
    t.add_argument("feedback", help="what the assistant should do differently")
    t.add_argument("--stage", default="04_semantic_episodic_procedural")
    t.set_defaults(func=cmd_teach)
    sub.add_parser("procedures").set_defaults(func=cmd_procedures)
    sub.add_parser("notify-test").set_defaults(func=cmd_notify_test)
    sub.add_parser("telegram-chat-id").set_defaults(func=cmd_telegram_chat_id)
    sub.add_parser("docs").set_defaults(func=cmd_docs)
    sub.add_parser("langfuse-models").set_defaults(func=cmd_langfuse_models)
    sub.add_parser("bot").set_defaults(func=cmd_bot)
    sub.add_parser("digest").set_defaults(func=cmd_digest)
    g = sub.add_parser("graph")
    g.add_argument("stage", nargs="?", help="e.g. 01_baseline (default: all built stages)")
    g.set_defaults(func=cmd_graph)
    p = sub.add_parser("prompts")
    p.add_argument("action", choices=["push", "pull", "history"])
    p.add_argument("name", nargs="?", help="prompt name, e.g. triage/system (default: all)")
    p.set_defaults(func=cmd_prompts)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
