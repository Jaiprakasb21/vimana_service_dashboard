# ESIGN_SERVICE Dashboard

This dashboard must be run from the local project folder and must use the local virtual environment only.

## Files

- `server.py`: backend server and DB query logic
- `index.html`, `styles.css`, `app.js`: dashboard UI
- `requirements.txt`: Python dependencies
- `menu.bat`: terminal menu for setup, start, and stop
- `manage.ps1`: PowerShell helper used by `menu.bat`

## Prerequisites

- Windows
- Python 3.10+ available on PATH
- Access to the DB config file already referenced in `server.py`

## Setup and Run

Open terminal in this folder and run:

```bat
menu.bat
```

You will get 3 options:

1. `Do setup`
2. `Start server`
3. `Stop server`

## Option Details

### 1. Do setup

This will:

- stop any tracked running server
- remove the current `.venv`
- recreate `.venv`
- reinstall packages from `requirements.txt`

This option always does a fresh reinstall.

### 2. Start server

This will:

- use `.venv\Scripts\python.exe`
- start `server.py`
- wait for `http://127.0.0.1:8010`
- open the dashboard in your default browser

### 3. Stop server

This will:

- stop the tracked dashboard server process
- remove the local PID file

## Requirements File

Dependencies are defined in:

```text
requirements.txt
```

Current dependency:

```text
PyMySQL
```

## Notes

- Always use `menu.bat` instead of running global Python directly.
- If setup fails, re-run option `1`.
- If browser opens but server is not reachable, run option `3` and then option `2`.
