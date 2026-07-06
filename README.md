# Vimana Service Dashboard (ESIGN_SERVICE / VERI5_LOCATION)

A local, self-contained Windows dashboard that queries production MySQL databases and shows
transaction success/failure counts and trends for two services, switchable from one UI:

- **ESIGN_SERVICE** — esign transaction success/failure counts, plus a breakdown of unique
  failure reasons and their counts.
- **VERI5_LOCATION** — reverse-geocoding (address ↔ lat/long) verification success/failure counts.
  (No failure-reason breakdown for this service — the source table has no error message/code column.)

This README is written so an automated agent (or a new engineer) can set this project up end to
end without asking questions. Follow the numbered steps in order.

## 1. Prerequisites

- Windows.
- Python 3.10+ available on `PATH` (used only to create the project's own virtual environment;
  the app never uses the global Python interpreter at runtime).
- Network access to the production MySQL host that hosts the `klpl_esign` and `kl_verification`
  databases.
- A JSON file with MySQL credentials (see step 2 — **do this before running setup**).

## 2. Point the DB credentials at this project (do this first)

`server.py` does **not** read credentials from an env var or a file inside this repo. It reads a
hardcoded absolute path defined at the top of `server.py`:

```python
CONFIG_PATH = Path(r"C:\Users\prakash.b\Documents\monthly_counts_script\proddb_counts _script\prodDbConfig.json")
```

To set this up on a machine/environment:

1. Create (or copy) a JSON file with exactly these four keys:
   ```json
   {
     "host": "<mysql host>",
     "port": 3306,
     "user": "<mysql user>",
     "password": "<mysql password>"
   }
   ```
   The `database` name is **not** part of this file — the app selects the database per-request
   (`klpl_esign` for ESIGN_SERVICE, `kl_verification` for VERI5_LOCATION); see `SERVICES` in
   `server.py`.
2. Point `CONFIG_PATH` in `server.py` at that file's real location — either:
   - place the file at the exact path already hardcoded above, or
   - edit the `CONFIG_PATH = Path(r"...")` line in `server.py` (near the top of the file) to the
     correct path for this environment.
3. **Never commit that credentials file into this repo.** `.gitignore` already excludes
   `prodDbConfig.json` and `*dbconfig*.json` as a safety net, but the file should live outside
   this project folder entirely (as it currently does) — this repo only stores a path, not the
   secret itself.

## 3. Files in this repo

- `server.py` — backend HTTP server (stdlib `http.server`, no framework) and all DB query logic
  for both services.
- `index.html`, `styles.css`, `app.js` — dashboard frontend (vanilla HTML/CSS/JS, no build step).
- `requirements.txt` — Python dependencies (installed into a local `.venv`, never globally).
- `menu.bat` — interactive terminal menu for setup/start/stop.
- `manage.ps1` — PowerShell implementation used by `menu.bat`.
- `.claude/launch.json` — dev-tooling config for previewing the app (not required to run it).
- `.gitignore` — excludes `.venv/`, `__pycache__/`, `.server.pid`, and any stray DB-credentials
  file that might get copied into this folder by mistake.

## 4. Setup and run

Open a terminal in this folder and run:

```bat
menu.bat
```

You get 4 options:

1. `Do setup`
2. `Start server`
3. `Stop server`
4. `Exit`

### Option 1 — Do setup

- Stops any tracked running server.
- Removes the current `.venv` (if present).
- Creates a fresh `.venv`.
- Installs everything in `requirements.txt` into that `.venv`.

This always does a clean reinstall — safe to re-run any time.

### Option 2 — Start server

- Uses `.venv\Scripts\python.exe` (never the global Python).
- Starts `server.py`.
- Polls `http://127.0.0.1:8010` until it responds (up to ~10s).
- Opens the dashboard in the default browser.
- Tracks the process PID in `.server.pid`.

### Option 3 — Stop server

- Stops the tracked dashboard server process (via `.server.pid`, falling back to whatever process
  is listening on port `8010`).
- Removes `.server.pid`.

### Equivalent manual setup (no menu.bat)

If running non-interactively (e.g. from an automation script), the equivalent commands are:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe server.py
```

The server listens on `http://127.0.0.1:8010` and serves the frontend at `/`.

## 5. Using the dashboard

- **Service** dropdown switches between `ESIGN_SERVICE` and `VERI5_LOCATION` — this changes which
  database/table is queried and which UI panels are shown (the "Failure reasons" panel only
  applies to ESIGN_SERVICE).
- **Client code** dropdown / search box filters to one client, or `ALL` for every client in
  `CLIENT_CODES` (defined in `server.py`).
- **From date / To date** use the browser's native date picker; the server converts these to the
  exact timestamp boundaries each service's underlying query needs.
- **Run** / **Refresh** re-fetch data for the current filters. **Reset** restores default filters.
  **Export** downloads the current per-client breakdown as CSV.

## 6. Backend API (for reference / automation)

- `GET /api/clients` → `{"clients": [...]}` — the fixed client-code list.
- `GET /api/dashboard?service=esign|location&from=YYYY-MM-DD&to=YYYY-MM-DD&clientCode=ALL|<code>`
  → `{"filters", "summary", "clients", "trend", "tiles", "failureReasons"}`.
  `failureReasons` is always `[]` for `service=location`.
- `GET /api/export.csv?service=...&from=...&to=...&clientCode=...` → CSV download of the
  per-client breakdown.

## 7. Data sources (for context)

- **ESIGN_SERVICE** — `klpl_esign` DB: `esign_transaction` joined to `esp_response`
  (`status = 1` success / `status = 0` failure) for counts, plus `doc_metadata.failure_reason`
  for the failure-reason breakdown.
- **VERI5_LOCATION** — `kl_verification` DB: `user_txn` filtered to
  `verification_type = 'LOCATION'`, `status = 'SUCCESS'` / `status = 'FAIL'`.

## 8. Troubleshooting

- Always use `menu.bat` (or the manual venv commands above) instead of running global Python
  directly — the app depends on packages installed into its own `.venv`.
- If setup fails, re-run option `1`.
- If the browser opens but the server isn't reachable, run option `3` then option `2`.
- If the dashboard loads but shows a "Database error", double-check step 2 — either the
  credentials file is missing/malformed, or `CONFIG_PATH` in `server.py` doesn't point at it.
