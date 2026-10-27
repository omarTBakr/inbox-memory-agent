# All configuration comes from .env (see .env.example); every variable is
# exported to the commands below, so Python and docker compose see the same values.
ifneq (,$(wildcard .env))
include .env
export
endif

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
CLI     := $(PY) -m email_assistant.cli
COMPOSE := docker compose
# mlflow run executes MLproject commands with plain `python`; make that the venv one
MLFLOW_RUN := PATH="$(CURDIR)/$(VENV)/bin:$$PATH" $(VENV)/bin/mlflow run . --env-manager local --experiment-name $(MLFLOW_EXPERIMENT_NAME)

.DEFAULT_GOAL := help
.PHONY: help setup env venv install up up-ollama down logs ps db-shell pull-models db-init \
        check-env profile test prompts-push prompts-pull prompts-history \
        stage1 stage2 stage3 stage4 stage-local graph memory-list memory-clear feedback teach procedures notify-test telegram-chat-id \
        api ui-install ui-dev ui-build app config-import docs bot digest langfuse-models gmail-auth worker mlflow-ui langfuse-ui clean

help: ## List targets
	@grep -E '^[a-zA-Z0-9_ -]+:.*?## ' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- Setup ----------
setup: env venv install ## First-time setup: .env, virtualenv, dependencies

env: ## Create .env from .env.example with generated secrets and passwords
	@$(PYTHON) src/email_assistant/envfile.py .env.example .env

venv: ## Create the virtualenv
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)

install: venv ## Install the package and dev dependencies
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev]"

# ---------- Infrastructure ----------
up: ## Start postgres, mlflow and the langfuse stack (Ollama runs on the host)
	$(COMPOSE) up -d

up-ollama: ## Same as `up` plus an Ollama container (stop host Ollama first)
	$(COMPOSE) --profile ollama up -d

down: ## Stop all containers (data volumes are kept)
	$(COMPOSE) --profile ollama down

logs: ## Follow container logs (S=<service> for one service)
	$(COMPOSE) logs -f $(S)

ps: ## Show container status
	$(COMPOSE) ps

db-shell: ## psql into the memory database
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

pull-models: ## Pull the chat and embedding models into Ollama
	ollama pull $(LLM_MODEL)
	ollama pull $(EMBEDDING_MODEL)

db-init: ## Create LangGraph store + checkpointer tables in Postgres
	$(CLI) db-init

memory-list: ## Show stored long-term memories, e.g. make memory-list KIND=semantic
	$(CLI) memory list $(KIND)

feedback: ## Record the right triage label for a sample email, e.g. make feedback EMAIL=newsletter LABEL=ignore
	$(CLI) feedback $(EMAIL) $(LABEL)

teach: ## Procedural feedback, e.g. make teach EMAIL=meeting-request FEEDBACK="Always propose two time options"
	$(CLI) teach $(EMAIL) "$(FEEDBACK)"

procedures: ## Show the live triage rules / agent instructions and their versions
	$(CLI) procedures

notify-test: ## Send a test push to the profile's channels (prints only if NOTIFY_DRY_RUN=true)
	$(CLI) notify-test

telegram-chat-id: ## List Telegram chat ids that messaged your bot (send it /start first)
	$(CLI) telegram-chat-id

memory-clear: ## Delete stored memories (all or KIND=...); requires CONFIRM=yes
	@test "$(CONFIRM)" = yes || { echo "This deletes memories. Re-run with CONFIRM=yes"; exit 1; }
	$(CLI) memory clear $(KIND)

# ---------- Checks ----------
check-env: ## Validate .env (required values, secrets, enabled integrations)
	$(CLI) check-env

profile: ## Print the user profile and the resolved settings (secrets masked)
	$(CLI) profile

test: ## Run tests
	$(PY) -m pytest -q

# ---------- Prompts ----------
prompts-push: ## Push prompts/ to Langfuse (new version only when content changed)
	$(CLI) prompts push

prompts-pull: ## Overwrite prompts/ with the PROMPT_LABEL versions from Langfuse
	$(CLI) prompts pull

prompts-history: ## Show Langfuse version history, e.g. make prompts-history NAME=triage/system
	$(CLI) prompts history $(NAME)

# ---------- Stages (tracked and triggered through MLflow) ----------
stage1 stage2 stage3 stage4: check-env ## Run a stage as an MLflow project run
	$(MLFLOW_RUN) -e $@ --run-name $@

stage-local: ## Run a stage script directly, e.g. make stage-local N=1
	$(PY) $(wildcard stages/0$(N)_*.py)

graph: ## Render stage graphs to docs/graphs (Mermaid + PNG), e.g. make graph STAGE=01_baseline
	$(CLI) graph $(STAGE)

# ---------- Web UI ----------
api: ## Run the API with auto-reload (http://$(API_HOST):$(API_PORT)/docs)
	$(PY) -m uvicorn email_assistant.api.main:app --host $(API_HOST) --port $(API_PORT) --reload --reload-dir src

ui-install: ## Install the UI's npm packages
	cd ui && npm install --no-fund --no-audit

ui-dev: ## Run the UI dev server (proxies /api to the API); open http://localhost:$(UI_PORT)
	cd ui && npm run dev

ui-build: ## Type-check and build the UI into ui/dist
	cd ui && npm run build

app: ui-build ## Serve the built UI and the API together on http://$(API_HOST):$(API_PORT)
	UI_BASE_URL= $(PY) -m uvicorn email_assistant.api.main:app --host $(API_HOST) --port $(API_PORT)

appimage: ui-build ## Build dist/EmailAssistant-<version>-x86_64.AppImage (see docs/APPIMAGE.md)
	APPIMAGE_BUILD_DIR="$(CURDIR)/$(APPIMAGE_BUILD_DIR)" APPIMAGE_OUTPUT_DIR="$(CURDIR)/$(APPIMAGE_OUTPUT_DIR)" \
		packaging/appimage/build.sh

langfuse-models: ## Sync config/model_prices.yml into Langfuse so local models get a cost
	$(CLI) langfuse-models

bot: ## Telegram feedback listener without the API (the API runs it itself)
	$(CLI) bot

digest: ## Send the ignored-email digest now
	$(CLI) digest

docs: ## Render config/guides.yml to docs/SETUP_GUIDE.md
	$(CLI) docs

config-import: ## Copy config/user_profile.yml into the UI config store
	$(CLI) config-import

# ---------- Application ----------
gmail-auth: ## One-time Gmail OAuth; writes GMAIL_TOKEN_PATH
	$(CLI) gmail-auth

worker: check-env ## Run the Gmail worker as an MLflow project run
	$(MLFLOW_RUN) -e worker --run-name worker

mlflow-ui: ## Open the MLflow UI
	xdg-open $(MLFLOW_TRACKING_URI)

langfuse-ui: ## Open the Langfuse UI
	xdg-open $(LANGFUSE_HOST)

# ---------- Housekeeping ----------
clean: ## Remove caches and build artefacts
	rm -rf build dist
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name '*.egg-info' \) -prune -exec rm -rf {} +
