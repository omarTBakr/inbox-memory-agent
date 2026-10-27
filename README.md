# Email Agent Assistant with Long-Term Memory (LangGraph)

An email assistant built up in stages, ending as a Gmail-connected worker:

| Stage | Script | Adds |
|---|---|---|
| 01 | `stages/01_baseline.py` | triage router (ignore / notify / respond) + response agent with tools |
| 02 | `stages/02_semantic_memory.py` | semantic memory: facts about contacts and projects |
| 03 | `stages/03_semantic_episodic.py` | episodic memory: past labelled emails as few-shot examples |
| 04 | `stages/04_semantic_episodic_procedural.py` | procedural memory: feedback rewrites triage rules / instructions; `notify_user` pushes what was done to Telegram |

## Stack
- **Ollama** – local chat model + embeddings
- **PostgreSQL + pgvector** – LangGraph store (long-term memory) and checkpointer
- **Langfuse** (self-hosted, v4) – LLM traces, feedback scores and prompt version history: see **[docs/LANGFUSE.md](docs/LANGFUSE.md)** for what's recorded and the metrics to watch
- **MLflow** – one tracked run per stage / worker execution (`MLproject` entry points)
- **Gmail API** – inbox ingestion (worker)

## Web UI
Step-by-step setup (Telegram bot, Google OAuth, models, troubleshooting): **[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)**,
also shown in the UI under "What should I do?" on each step. Edit `config/guides.yml`, then `make docs`.

```bash
make api       # FastAPI on http://127.0.0.1:8000 (docs at /docs)
make ui-dev    # React UI on http://localhost:5173 (proxies /api)
make app       # or: build the UI and serve everything from the API
```
Setup wizard: System → Profile → Notifications (Telegram tests) → Gmail (OAuth, approval mode)
→ Calendar → Model (Ollama or API, compatibility test) → Embeddings → Review (dry run on sample emails).
Forms are generated from the pydantic models in `src/email_assistant/config_models.py`; choices come from `config/options.yml`.
What the UI saves goes to Postgres (`app_config`, versioned; secrets encrypted in `app_secrets` with `APP_ENCRYPTION_KEY`);
until a section is saved, `config/user_profile.yml` and `.env` are used. `make config-import` copies the YAML profile in.

## Setup: Telegram bot
The assistant tells you on Telegram what it did, with buttons to correct it (👍 / 👎 / ignore · notify · respond).

1. In Telegram open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Choose a display name, then a username ending in `bot` (e.g. `my_inbox_assistant_bot`).
3. BotFather replies with a **token** like `123456789:AA...`. Keep it secret: anyone with it controls the bot.
4. Open your new bot (BotFather's reply links it) and press **Start**. A bot can only message people who started it.
5. In the app: **Setup → Notifications**, choose channel `telegram` and paste the token into **Telegram bot token**.
6. Press **Detect Telegram chat id** and pick your chat. If nothing shows up, send the bot any message and detect again.
   From the terminal: `make telegram-chat-id`.
7. Turn **Dry run** off, press **Save**, then **Test telegram**. A test message should arrive.

If the token ever leaks (pasted in a chat, committed...), send `/revoke` to BotFather and paste the new token in the app.
Only your chat id can give feedback; messages from other chats are ignored.

## Setup: Gmail API (OAuth client JSON and test users)
The app reads your mail with your own Google Cloud OAuth client. It's free and needs no Google verification for personal use.

**1 · Create a project and enable the APIs**
1. Open [Google Cloud Console](https://console.cloud.google.com/), then the project picker → **New project** → any name → **Create**.
2. With that project selected, open the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) page and press **Enable**.
3. Optional, for calendar features: enable the [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) too.

**2 · Consent screen, and add your Gmail address as a test user**
1. Open [Google Auth Platform → Overview](https://console.cloud.google.com/auth/overview) (older consoles call it *OAuth consent screen*) and press **Get started**.
2. App name: anything (e.g. *Email Assistant*). Support email: yours. **Audience: External**. Contact email: yours. Accept and **Create**.
3. Open [Audience](https://console.cloud.google.com/auth/audience). Under **Test users** press **+ Add users**, enter the Gmail address
   the assistant will read (the one you will sign in with), and **Save**.
   The app stays in *Testing* mode, where only these test users can sign in. Without this step Google shows
   *"Error 403: access_denied … has not completed the Google verification process"*.

**3 · Create the OAuth client and download the JSON**
1. Open [Clients](https://console.cloud.google.com/auth/clients) → **+ Create client**.
2. Application type **Web application**. Under **Authorized redirect URIs** add exactly
   `http://localhost:8000/api/gmail/oauth/callback` (it must match `GOOGLE_OAUTH_REDIRECT_URL` in `.env`).
   *Alternative:* type **Desktop app** (no redirect URI) and connect from the terminal with `make gmail-auth`.
3. Press **Create**, then **Download JSON** in the dialog (or the ⬇ icon in the client list later).
   The file is named like `client_secret_….apps.googleusercontent.com.json`. Never commit it.

**4 · Connect**
1. In the app: **Setup → Gmail → Upload client JSON** and pick the downloaded file. It is stored encrypted in Postgres.
2. Press **Connect Google** and sign in with the test-user address. Google warns *"Google hasn't verified this app"*:
   it is your own app, so press **Advanced → Go to *(app name)* (unsafe)** and allow access.
3. Back in the app, press **Test connection**. It shows your address and unread count.

| Error | Fix |
|---|---|
| `Error 400: redirect_uri_mismatch` | The client is a Desktop app, or the Web client lacks the exact redirect URI above |
| `Error 403: access_denied` | Add your address under **Audience → Test users** |
| *Gmail API has not been used in project…* | Enable the Gmail API (step 1) and retry after a minute |
| `invalid_grant` after about a week | Testing-mode tokens expire after 7 days: press **Reconnect Google** |

More detail, including Telegram Saved Messages and the calendar: [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md).

## Configuration
Code reads configuration only through three sources (a UI will edit these later):

| Source | Loaded by | Holds |
|---|---|---|
| `.env` (template: `.env.example`) | `settings.get_settings()` | models, infrastructure, memory and episodic tuning, Gmail |
| `config/user_profile.yml` | `profile.load_profile()` | who the user is, writing style, contacts, triage rules, scheduling |
| `prompts/*.yml` (+ Langfuse versions) | `prompts.get_prompt()` | every text sent to a model |

Stages are registered once in `src/email_assistant/stages.py`.

## Memory & feedback
- `make memory-list [KIND=semantic|episodic]`, `make memory-clear CONFIRM=yes [KIND=...]`
- `make feedback EMAIL=<sample id> LABEL=ignore|notify|respond` stores a labelled example (episodic memory, stage 03+)
- `make teach EMAIL=<sample id> FEEDBACK="..."` rewrites the procedures the feedback is about (stage 04); `make procedures` shows the live ones, history is in Langfuse as `procedural/<user id>/<name>`
- `make graph` renders every stage graph to `docs/graphs/`

## Notifications (stage 04)
- Settings > Notifications: channels (`telegram` bot, `telegram_self` Saved Messages), which triage outcomes to push (`notify_on`), Telegram chat id
- Secrets (bot token, api_hash) are saved encrypted from the UI; `NOTIFY_DRY_RUN=true` prints instead of sending
- Telegram: create a bot with @BotFather, send it /start, run `make telegram-chat-id`
- `make notify-test` sends a test message; texts live in `prompts/notifications/`

## Gmail: auto-trigger and Spam
- Settings > Gmail > *Watch for new mail*: switch on and every new email matching `query` is handled as it arrives (Gmail change history, checked every `poll_seconds`), each exactly once (`gmail_messages` queue in Postgres). Runs inside the API; `make worker` runs the same watcher on its own.
- *Include Spam* also checks new Spam (`spam_query`). Spam emails are reported at most and never answered (enforced in the triage router). Their Telegram message has **📥 Not spam**, which moves the email to the Inbox and teaches the assistant it mattered.

## AppImage (any Linux)
`make appimage` builds `dist/EmailAssistant-<version>-x86_64.AppImage`: Python, the backend and the UI in one file. It starts the Docker services and opens the app in the browser. See [docs/APPIMAGE.md](docs/APPIMAGE.md).

## Layout
```
config/user_profile.yml   who the assistant works for
prompts/                  one YAML per prompt, synced to Langfuse (see prompts/README.md)
data/sample_emails.yml    offline test emails
src/email_assistant/      shared package (settings, profile, llm, prompts, tracing, memory, tools, graph, gmail)
stages/                   stage runners
docker-compose.yml        postgres, mlflow, langfuse stack, optional ollama
Makefile                  every task; reads .env
```

## Quick start
```bash
make setup          # .env (with generated secrets), .venv, dependencies
# edit .env passwords and config/user_profile.yml TODOs
make up             # postgres, mlflow (localhost:5000), langfuse (localhost:3000)
make pull-models    # ollama models from .env
make check-env db-init prompts-push
make stage1         # run a stage as an MLflow run
make help           # all targets
```
