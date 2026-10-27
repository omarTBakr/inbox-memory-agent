"""AppImage entry point: first-run setup, Docker services, then the API + UI in the browser.

    EmailAssistant.AppImage [--no-browser] [--no-services] [--import-env FILE] [--stop-services] [--version]

Read-only files (prompts, config defaults, built UI, docker-compose.yml) come from the
bundle; everything the user owns lives in $XDG_CONFIG_HOME/email-assistant:
    .env       generated on first run (fresh passwords and keys), or imported with --import-env
    secrets/   Google OAuth files when the file fallback is used
Settings saved in the UI live in Postgres, as when running from source.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from importlib.metadata import version
from pathlib import Path

RESOURCES = Path(os.environ.get("APPDIR", Path(__file__).resolve().parents[2])) / "opt" / "email-assistant"
HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "email-assistant"
ENV_FILE = HOME / ".env"
# written at runtime, so they must not resolve inside the read-only bundle
WRITABLE = {"GMAIL_CREDENTIALS_PATH": "secrets/credentials.json", "GMAIL_TOKEN_PATH": "secrets/token.json"}


def log(message: str) -> None:
    print(f"[email-assistant] {message}", flush=True)


def first_run(import_env: Path | None) -> None:
    from email_assistant import envfile

    if import_env:
        if ENV_FILE.exists():
            sys.exit(f"{ENV_FILE} already exists; move it away first to import another one")
        HOME.mkdir(parents=True, exist_ok=True)
        shutil.copy(import_env, ENV_FILE)
        ENV_FILE.chmod(0o600)
        log(f"Imported {import_env} -> {ENV_FILE}")
    elif envfile.create(RESOURCES / ".env.example", ENV_FILE):
        log(f"First run: created {ENV_FILE} with generated passwords (edit it to change settings)")
    (HOME / "secrets").mkdir(parents=True, exist_ok=True)


def load_env() -> dict[str, str]:
    """The user's .env into the process environment (variables already set win), like `make` does;
    returns the resulting environment."""
    from dotenv import dotenv_values

    values = {k: v for k, v in dotenv_values(ENV_FILE, interpolate=True).items() if v is not None}
    for key, default in WRITABLE.items():
        path = Path(values.get(key) or default)
        values[key] = str(path if path.is_absolute() else HOME / path)
    values.update(APP_RESOURCES=str(RESOURCES), APP_ENV_FILE=str(ENV_FILE), UI_BASE_URL="")
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return dict(os.environ)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def compose(*args: str) -> int:
    command = ["docker", "compose", "-f", str(RESOURCES / "docker-compose.yml"), "--env-file", str(ENV_FILE), *args]
    log(" ".join(command[:2] + list(args)))
    return subprocess.call(command)


def start_services(env: dict[str, str]) -> None:
    host, port = env.get("POSTGRES_HOST", "localhost"), int(env.get("POSTGRES_PORT", "5433"))
    if port_open(host, port):
        return
    if not shutil.which("docker"):
        log("Docker not found: start Postgres/Langfuse/MLflow yourself; the System step in the app shows what is missing")
        return
    if compose("up", "-d") != 0:
        log("docker compose failed; the app starts anyway (see the System step)")
        return
    for _ in range(60):
        if port_open(host, port):
            return
        time.sleep(1)
    log(f"Postgres is not reachable on {host}:{port} yet")


def init_database() -> None:
    try:
        from email_assistant.memory.store import setup_database

        setup_database()
    except Exception as e:  # the System step offers "Initialise database" later
        log(f"Database not initialised yet: {e}")


def open_browser(url: str, host: str, port: int) -> None:
    for _ in range(60):
        if port_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(prog="EmailAssistant.AppImage", description=__doc__.splitlines()[0])
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--no-services", action="store_true", help="don't start the Docker services")
    parser.add_argument("--import-env", type=Path, help="use an existing .env (e.g. the project's) on first run")
    parser.add_argument("--stop-services", action="store_true", help="stop the Docker services and exit")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(version("email-assistant"))
        return

    first_run(args.import_env)
    env = load_env()
    if args.stop_services:
        sys.exit(compose("down"))
    if not args.no_services:
        start_services(env)
    init_database()

    import uvicorn

    host, port = env.get("API_HOST", "127.0.0.1"), int(env.get("API_PORT", "8000"))
    if port_open(host, port):
        sys.exit(f"Port {port} is already in use (is the app already running?). Set API_PORT in {ENV_FILE}.")
    if not args.no_browser:
        browse_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        threading.Thread(target=open_browser, args=(f"http://{browse_host}:{port}/setup", host, port), daemon=True).start()
    log(f"Serving on http://{host}:{port} (Ctrl+C to stop; containers keep running, --stop-services stops them)")
    uvicorn.run("email_assistant.api.main:app", host=host, port=port, log_level=env.get("LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
