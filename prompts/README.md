# Prompts

One YAML file per prompt, grouped by the part of the application that uses it:

| Folder | Used by |
|---|---|
| `triage/` | triage router (ignore / notify / respond) |
| `response_agent/` | agent that drafts replies and schedules meetings |
| `memory/` | semantic memory instructions, episodic few-shot formatting |
| `procedural/` | optimizer that rewrites triage rules / agent instructions from feedback |

## File format
```yaml
name: triage/system          # must equal the path without .yml
type: text                   # text | chat
description: ...
variables: [name, ...]       # placeholders used in template
config: {temperature: 0}     # model params / metadata stored with each version
template: |
  ... {{name}} ...           # Langfuse {{variable}} syntax
```

## History
- **git** tracks every edit to these files.
- **Langfuse** keeps numbered versions: `make prompts-push` creates a new version only when `template` or `config` changed and labels it `PROMPT_LABEL`. Procedural memory also writes its optimized prompts there.
- `make prompts-history NAME=triage/system` lists versions; `make prompts-pull` writes the labelled Langfuse version back into these files.
- `PROMPT_SOURCE=langfuse` in `.env` makes the app read prompts from Langfuse instead of these files.
