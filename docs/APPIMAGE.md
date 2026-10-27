# AppImage: run the assistant on any Linux

`make appimage` packs the whole app into one executable file,
`dist/EmailAssistant-<version>-x86_64.AppImage`:

| Inside the AppImage | Comes from the machine it runs on |
|---|---|
| Python 3.12 (python-build-standalone), every Python dependency | **Docker** with the compose plugin: Postgres, Langfuse, MLflow |
| Backend (FastAPI), built UI, prompts, config defaults, docs | **Ollama**, if you use local models (or choose an API model in Setup → Model) |
| `docker-compose.yml`, `.env.example` | A browser |

Target: x86_64 Linux with glibc ≥ 2.17 (practically every distribution since 2014). No FUSE
needed with `--appimage-extract-and-run`.

## Build
```bash
make appimage
```
1. Builds the UI (`make ui-build`).
2. Downloads, once, into `build/appimage/cache/`, and checks each against its pinned SHA256:
   - `APPIMAGE_PYTHON_URL`, a relocatable CPython (~67 MB)
   - `APPIMAGETOOL_URL`, appimagetool 1.9.1 (~15 MB)
3. Installs the project into that Python, copies the resources into `AppDir/opt/email-assistant/`,
   and packs `dist/EmailAssistant-<version>-x86_64.AppImage`.

To upgrade Python or appimagetool, change the URL **and** the SHA256 in `.env` (both are
listed on the GitHub release page).

## Run
```bash
chmod +x EmailAssistant-0.1.0-x86_64.AppImage
./EmailAssistant-0.1.0-x86_64.AppImage
```
On every start it:
1. On the first run, creates `~/.config/email-assistant/.env` from `.env.example` with freshly
   generated passwords and keys.
2. Starts the Docker services (`docker compose up -d`, project `email-assistant`) if Postgres isn't reachable.
3. Creates or migrates the database tables.
4. Serves the API and UI on `http://localhost:8000` and opens `/setup` in the browser.

Ctrl+C stops the app. The containers keep running; stop them with `--stop-services`.

| Option | |
|---|---|
| `--no-browser` | don't open the browser (headless / server use) |
| `--no-services` | don't start Docker services (they run elsewhere; set hosts in the `.env`) |
| `--import-env FILE` | first run only: use an existing `.env` instead of generating one |
| `--stop-services` | `docker compose down` (data volumes are kept) and exit |
| `--version` | print the version |
| `--appimage-extract-and-run` | run without FUSE |

### Where your data lives
| What | Where |
|---|---|
| Settings, secrets (encrypted), memory, feedback, Gmail queue | Postgres (Docker volume `email-assistant_postgres_data`) |
| Traces | Langfuse volumes (`email-assistant_clickhouse_data`, ...) |
| `.env`, OAuth file fallback (`secrets/`) | `~/.config/email-assistant/` |

### Same machine as the source checkout
The AppImage uses the same compose project (`email-assistant`), so it reuses the existing
containers and data. Their passwords are in the project's `.env`, so import it on the first run:
```bash
./EmailAssistant-0.1.0-x86_64.AppImage --import-env "/path/to/project/.env"
```
Without it, the generated passwords won't match the existing Postgres volume.

### Uninstall
`--stop-services`, then delete the AppImage and `~/.config/email-assistant/`. To delete all
data too: `docker volume ls | grep email-assistant` and `docker volume rm` the volumes.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `dlopen(): error loading libfuse.so.2` | run with `--appimage-extract-and-run`, or install `fuse2`/`libfuse2` |
| `Port 8000 is already in use` | another copy is running, or `make api` is; set `API_PORT` in `~/.config/email-assistant/.env` |
| Postgres "password authentication failed" | the `.env` doesn't match an existing volume: see *Same machine as the source checkout* |
| Gmail "redirect_uri_mismatch" after changing `API_PORT` | update `GOOGLE_OAUTH_REDIRECT_URL` and the redirect URI of your Google OAuth client |
| System step shows Ollama red | install and start Ollama, or pick an API model in Setup → Model |
