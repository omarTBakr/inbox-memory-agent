"""Create a .env from .env.example with fresh secrets (standard library only).

Used by `make env` (before the virtualenv exists) and by the AppImage launcher:
    python src/email_assistant/envfile.py .env.example .env [KEY=VALUE ...]
Generated: Langfuse encryption key / NextAuth secret / salt, the app's Fernet key, and a
random password for every value left as `change-me`. KEY=VALUE pairs override lines
(e.g. absolute paths for a packaged install). An existing target is never overwritten.
"""

import base64
import re
import secrets
import sys
from pathlib import Path

PLACEHOLDER = "change-me"
GENERATED = {
    "LANGFUSE_ENCRYPTION_KEY": lambda: secrets.token_hex(32),
    "LANGFUSE_NEXTAUTH_SECRET": lambda: base64.b64encode(secrets.token_bytes(32)).decode(),
    "LANGFUSE_SALT": lambda: base64.b64encode(secrets.token_bytes(32)).decode(),
    "APP_ENCRYPTION_KEY": lambda: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
}
_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def render(example: str, overrides: dict[str, str] | None = None) -> str:
    overrides = overrides or {}
    lines = []
    for line in example.splitlines():
        match = _LINE.match(line)
        if match:
            key, value = match.groups()
            if key in overrides:
                value = overrides.pop(key)
            elif key in GENERATED and not value:
                value = GENERATED[key]()
            elif value == PLACEHOLDER:
                value = secrets.token_urlsafe(18)
            line = f"{key}={value}"
        lines.append(line)
    lines += [f"{k}={v}" for k, v in overrides.items()]  # overrides not in the example
    return "\n".join(lines) + "\n"


def create(example: Path, target: Path, overrides: dict[str, str] | None = None) -> bool:
    """Write `target` unless it exists; returns whether it was created."""
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(example.read_text(), overrides))
    target.chmod(0o600)
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pairs = dict(arg.split("=", 1) for arg in sys.argv[3:])
    if create(Path(sys.argv[1]), Path(sys.argv[2]), pairs):
        print(f"Created {sys.argv[2]} with generated secrets and passwords")
    else:
        print(f"{sys.argv[2]} already exists, leaving it untouched")
