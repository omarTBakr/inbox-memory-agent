"""Setup guides (config/guides.yml): served to the UI and rendered to docs/SETUP_GUIDE.md."""

import yaml

from email_assistant.settings import get_settings


def load() -> dict:
    s = get_settings()
    return yaml.safe_load(s.path(s.guides_path).read_text())


def to_markdown(guides: dict | None = None) -> str:
    guides = guides or load()
    lines = [
        "# Setup guide",
        "",
        "<!-- Generated from config/guides.yml by `make docs`; edit that file instead. -->",
        "",
        guides["intro"],
        "",
    ]
    for number, step in enumerate(guides["steps"].values(), start=1):
        lines += [f"## {number}. {step['title']}", ""]
        for section in step["sections"]:
            lines += [f"### {section['title']}", ""]
            lines += [f"{i}. {text}" for i, text in enumerate(section["steps"], start=1)]
            lines += [""]
            if section.get("notes"):
                lines += [f"> {note}  " for note in section["notes"]]
                lines += [""]
    return "\n".join(lines).rstrip() + "\n"


def write_markdown() -> str:
    s = get_settings()
    path = s.path(s.setup_guide_doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_markdown())
    return str(path)
