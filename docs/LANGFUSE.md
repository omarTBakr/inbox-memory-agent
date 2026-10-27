# Langfuse: tracing, feedback scores and prompt history

Langfuse records every model call the assistant makes, the feedback you give, and every
version of every prompt. Use it to answer three questions: **is the assistant doing the
right thing, is it getting better, and what changed when it got worse?**

| | |
|---|---|
| URL | http://localhost:3000 (`make langfuse-ui`) |
| Login | `LANGFUSE_INIT_USER_EMAIL` / password from `.env` (created on first start; change it in the UI) |
| Server | Langfuse **4.70.1** (`LANGFUSE_VERSION`), ClickHouse **25.12** (`CLICKHOUSE_VERSION`), self-hosted in `docker-compose.yml` |
| Python SDK | `langfuse` 5.x; one client configured from settings in `email_assistant/tracing.py` (`langfuse_client()`) |
| On/off | `LANGFUSE_ENABLED=true` in `.env` |
| Environment | `APP_ENV` in `.env` (`development`, `staging`, `production`, ...) on every trace, score and MLflow run |

### Inside the app: Visualizations tab
The app's **Visualizations** tab (http://localhost:5173/visualizations) shows:
- **Headline numbers** for the chosen period and environment, from the Langfuse metrics API:
  feedback score, triage mix, cost, p95 latency, tokens and notification warnings, each with a
  daily sparkline. Clicking a tile opens the matching Langfuse page below.
- **The Langfuse UI itself** (Traces · Scores · Prompts · Dashboards · Sessions), embedded.

Langfuse forbids being framed (`frame-ancestors 'none'`), so the tab goes through the
`langfuse-embed` proxy (`LANGFUSE_EMBED_URL`, port 3002). It changes only `frame-ancestors` to
`LANGFUSE_EMBED_ORIGINS` (the app's own addresses) and drops `X-Frame-Options`; every other
security header stays, and Langfuse on :3000 is unchanged. You need to be logged in to Langfuse
in the same browser (the login is shared across localhost ports): use *Log in to Langfuse*, then *Reload*.

---

## 1. What gets recorded

### One trace per email
Every email processed by a stage (samples, `make stageN`, or *Run on my latest Gmail emails*)
becomes one trace, created with a predefined trace id so feedback can find it later.

| Field | Value | Use it to |
|---|---|---|
| Name | `<stage>:<email ref>`, e.g. `04_semantic_episodic_procedural:gmail:1a17910cd032eb0e` | find the run for a specific email |
| Tags | the stage id | compare stages |
| Metadata | `email_id` | join with the Feedback page / Postgres `feedback_items` |

### Inside a trace (stage 04)
```
<stage>:<email ref>                         root
├─ triage_router                            ignore / notify / respond decision
│  └─ RunnableSequence
│     ├─ ChatOllama            GENERATION   prompt = rules + few-shot examples; output = JSON decision
│     └─ PydanticOutputParser               fails here if the model breaks the JSON schema
├─ response_agent                           only for "respond": explicit ReAct agent (graph/react_agent.py)
│  ├─ gather_context                        memories about the sender and subject
│  ├─ think                    GENERATION   Thought: known, missing, reason, next, tool, tool_input
│  ├─ act                                   one tool call: search_memory, manage_memory,
│  │                                        check_calendar_availability, schedule_meeting
│  ├─ (think → act repeats, at most REACT_MAX_STEPS)
│  ├─ draft_reply              GENERATION   Draft: to, subject, body, language, facts + sources, commitments
│  ├─ review                   GENERATION   deterministic checks, then the critic (ok / issues)
│  ├─ escalate                 GENERATION   holding reply when it must not decide (escalate_when)
│  └─ send                                  write_email with the reviewed draft
└─ notify_user                              builds the validated notification, pushes to Telegram
```
The generation name is the chat model class (`ChatOllama`, `ChatAnthropic`, ...); the model
name, token usage and latency are on the generation.

### Scores
| Score | Type | Written by | Meaning |
|---|---|---|---|
| `user_feedback` | NUMERIC 1 / 0 | 👍 / 👎 in Telegram or the Feedback page | 1 = right, 0 = wrong; the comment holds the correction ("should be notify") or your text |
| `triage_classification` | CATEGORICAL | `notify_user` | the decision: `ignore`, `notify`, `respond` |
| `notification_warnings` | NUMERIC count | `notify_user` | schema checks the run failed (reply to an address not in the email, unknown tool, "respond" without a reply); comment lists them |

### Prompts
- Every file in `prompts/` is a Langfuse prompt (`make prompts-push` adds a version only when it changed; label `production`).
- Procedural memory writes its rewrites as **`procedural/<user id>/<name>`** (e.g. `procedural/omar/agent_instructions`), commit message `v<n>: <your feedback>`.
- `make prompts-history NAME=<name>` lists versions from the terminal; the Prompts page shows diffs between versions.

### Environments
Every trace, generation and score carries `APP_ENV` as its Langfuse **environment**, and every
MLflow run has an `environment` tag. Use one value per deployment, e.g. `development` on your
laptop and `production` for the always-on worker, and pick the environment in the selector at
the top of the Langfuse UI. Everything recorded before environments were set is in `default`.

### Cost
Langfuse computes a cost for each generation from its model name and token usage at ingestion.
- **API models** (OpenAI, Anthropic, Gemini): priced by Langfuse's built-in model definitions.
- **Local Ollama models**: priced by `config/model_prices.yml`, synced with `make langfuse-models`.
  The default is 0. Set an estimated GPU/electricity cost per 1M tokens to compare local and API
  models fairly. Any model name of the form `name:tag` matches.
- Prices apply to generations ingested **after** they are set; older ones keep no cost.
- **Cost per environment**: select the environment at the top of the UI, then use a dashboard
  widget "Observations · sum of total cost · per day", or group the cost widget by environment.

---

## 2. Essential metrics to watch

| # | Metric | Where | Healthy | When it's off |
|---|---|---|---|---|
| 1 | **Feedback score**: average `user_feedback`, and how many ratings | Scores, or a dashboard widget (below) | ≥ 0.8 average over 7 days | Read the 👎 comments (Scores table, comment column). Several on the same kind of email → check whether the correction reached memory (Feedback page, "Memory changed" column). |
| 2 | **Triage mix**: share of `triage_classification` values | Dashboard widget, grouped by value | Stable week to week; mostly `ignore` for a typical inbox | A jump in `respond` → rules too loose or a procedural rewrite went wrong (check `procedural/*` versions). A jump in `ignore` → important mail at risk; check the ignored digest for 👎. |
| 3 | **Notification warnings**: traces with `notification_warnings` > 0 | Traces filtered by that score | Always 0 | Open the trace. A reply to an unknown address or an unknown tool means the agent made something up; tighten `prompts/response_agent/system.yml` or teach with feedback. |
| 4 | **Latency**: p50 / p95 per trace; triage generation latency | Traces list (latency column), dashboard | Local `gemma4:e4b`: triage ~5–10 s, a reply ~15–40 s | p95 well above that: model too large for the GPU, `LLM_NUM_CTX` too big, or reasoning switched on. |
| 5 | **Input tokens vs context window**: input tokens per generation | Generation detail (usage) | Comfortably below `LLM_NUM_CTX` (8192) | **Ollama silently cuts the start of the prompt** when the input is too long, which loses the rules. Raise `LLM_NUM_CTX` or lower `GMAIL_MAX_BODY_CHARS`. |
| 6 | **Errors**: observations with level ERROR | Traces / Observations filtered by level | 0 | `PydanticOutputParser` errors mean the model ignored the JSON schema: run *Test this model* in Setup → Model and switch model or reasoning. Tool errors also appear in the run's `tool_errors` MLflow metric. |
| 7 | **ReAct behaviour**: number of `think` steps, tool calls, `review` rejections and escalations per reply | Trace tree; Telegram "Needs your decision" | 1–4 steps; review mostly ok first time; escalations only for `escalate_when` topics | Many review rejections → read the issues in `review` and tighten `prompts/response_agent/react_*`. Escalations for normal emails → the reviewer is too strict or a tool is missing information. |
| 8 | **Few-shot examples**: examples in the triage prompt | `triage_router` generation input, "Few shot examples" section | Present for emails similar to ones you rated | Missing for an email you corrected before → `EPISODIC_MIN_SCORE` is too high. |
| 9 | **Cost per environment** | Dashboard: sum of total cost per day, per environment | Within budget; `development` ≪ `production` | A model without a price shows no cost: add it to `config/model_prices.yml`, then run `make langfuse-models`. |
| 10 | **Effect of a prompt change**: `user_feedback` before vs after a new prompt or procedural version | Scores, filtered by time around the version's date (Prompts page) | Same or better after the change | Worse → roll back: set the `production` label on the previous version, or edit the file and `make prompts-push`. |

---

## 3. Dashboards worth creating

Dashboards → **New dashboard**, then **Add widget** for each:

| Widget | Data | Metric | Breakdown / filter | Chart |
|---|---|---|---|---|
| Feedback over time | Scores | average value | filter name = `user_feedback`; per day | line |
| Ratings count | Scores | count | filter name = `user_feedback`; group by value | bar |
| Triage mix | Scores | count | filter name = `triage_classification`; group by value | pie / stacked bar |
| Warnings | Scores | sum of value | filter name = `notification_warnings`; per day | bar |
| Latency p95 | Traces | p95 latency | group by trace tag (stage) | line |
| Tokens per email | Observations (generations) | sum of input / output tokens | per day | line |
| Cost per environment | Observations (generations) | sum of total cost | group by environment; per day | stacked bar |

Langfuse also ships default dashboards (latency, cost, usage, tool errors) that work with these traces as they are.

---

## 4. Recipes

**Why was this email ignored?**
Traces → search the email id → `triage_router` → `ChatOllama` input. You see the rules in
force (procedural memory), the few-shot examples (episodic memory) and the model's
reasoning. If the reasoning contradicts your rules, give 👎 → *Should be: notify* in the digest.

**What did my feedback change?**
Scores → `user_feedback` = 0 → the comment says what you asked. Then Prompts →
`procedural/<you>/...`: the new version's commit message is your feedback, and the diff
shows exactly what was rewritten.

**Find every run with a suspicious notification:**
Traces → filter by score `notification_warnings` > 0.

**Compare two models:**
Run the samples with each model (Setup → Model, then Review → *Dry run*) and compare
latency, tokens and errors per trace name in a dashboard; the MLflow run of each dry run
holds triage accuracy.

---

## 5. Operations

- **Upgrade:** check the official compose for the target version
  (https://github.com/langfuse/langfuse/blob/main/docker-compose.yml), especially the
  ClickHouse version and new required environment variables. Then set `LANGFUSE_VERSION` /
  `CLICKHOUSE_VERSION` in `.env` and run `make up`. Migrations run on startup; follow them
  with `make logs S=langfuse-worker`.
- **Back up before major upgrades:** `docker compose exec postgres pg_dump -U $POSTGRES_USER langfuse > langfuse.sql`
  (users, projects, prompts, scores config); traces live in the `clickhouse_data` volume.
- **Disable:** `LANGFUSE_ENABLED=false`. The app keeps working; prompts are read from `prompts/` (`PROMPT_SOURCE=local`).

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No traces at all | `make check-env`; keys in `.env` must match the project's API keys (created by `LANGFUSE_INIT_*` on first start). |
| "Langfuse client initialized without public_key" | Something used the SDK's global client before it was configured. Use `email_assistant.tracing.langfuse_client()` instead of `langfuse.get_client()`. |
| Traces appear late | Ingestion goes through the worker queue (seconds). `make logs S=langfuse-worker` shows its progress. |
| UI loads but is empty after an upgrade | Wait for the ClickHouse migrations to finish (worker logs), then reload. |
| `api.trace.get` missing in the SDK | Langfuse 4 is observation-first: use `api.observations.get_many(trace_id=...)` and `api.scores.get_many(trace_id=...)`. |
