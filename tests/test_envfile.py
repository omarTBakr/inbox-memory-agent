from email_assistant.envfile import create, render

EXAMPLE = "# comment\nPOSTGRES_PASSWORD=change-me\nAPP_ENCRYPTION_KEY=\nLANGFUSE_SALT=\nAPI_PORT=8000\nGMAIL_TOKEN_PATH=secrets/token.json\n"


def test_secrets_are_generated_and_placeholders_replaced():
    a, b = render(EXAMPLE), render(EXAMPLE)
    assert "change-me" not in a and a != b
    values = dict(line.split("=", 1) for line in a.splitlines() if "=" in line)
    assert values["API_PORT"] == "8000" and len(values["APP_ENCRYPTION_KEY"]) == 44 and values["LANGFUSE_SALT"]


def test_overrides_and_existing_file_kept(tmp_path):
    example, target = tmp_path / "example", tmp_path / "home" / ".env"
    example.write_text(EXAMPLE)
    assert create(example, target, {"GMAIL_TOKEN_PATH": "/abs/token.json", "EXTRA": "1"})
    text = target.read_text()
    assert "GMAIL_TOKEN_PATH=/abs/token.json" in text and text.endswith("EXTRA=1\n")
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert not create(example, target)
