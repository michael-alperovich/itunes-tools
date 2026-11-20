## itunes-tools 

This is a project that provides several applications for managing iTunes library.
Applications will be implemented using Python and PyQt. WinCom API will be used for communication with iTunes.
Pydantic will b

Applications will include:
- iTunes playlist manual sorter
- iTunes metadata verifier
- iTunes new song importer
- iTunes to Spotify sync (bidirectional)

### iTunes library contract

The applications rely on the iTunes library following the rules below. When a rule is broken, the
applications stop with an error that explains what to fix in iTunes, rather than guessing.
Custom metadata conventions will be documented here as they are introduced.

**Constraints**

- **Unique playlist names.** No two playlists, including folders and smart playlists, may share a
  name. Names are compared exactly, so `Rock` and `rock` are different names.
  Violations raise `DuplicatePlaylistNameError`, which lists the names to rename.

**Custom metadata**

None yet.

### Configuration

| Environment variable     | Default | Purpose                                                   |
|--------------------------|---------|-----------------------------------------------------------|
| `ITUNES_TOOLS_LOG_LEVEL` | `DEBUG` | Log level for the applications (`INFO`, `WARNING`, ...). |

### Development

Requires Windows, Python 3.14 and [uv](https://docs.astral.sh/uv/). Run the commands below from the
repository root in PowerShell.

**Setup**

The project's virtual environment lives outside the repository. Set its location once per shell
before running any `uv` command (skip this to use uv's default `.venv` instead):

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'D:\venv\itunes-tools'
uv sync --locked
uv run pre-commit install
```

`pre-commit install` adds a git hook that checks formatting and imports on every commit. It reports
problems without changing files, so fix them with the commands below and commit again.

**Testing**

Tests use pytest and live under `tests/`, mirroring `src/`. Unit tests replace iTunes COM with
fakes from `tests/conftest.py`. Integration tests carry the `itunes` marker, need a real iTunes,
and are skipped by default. They are read-only, but they start iTunes if it is not running.

| Command                     | Runs                                |
|-----------------------------|-------------------------------------|
| `uv run pytest`             | Unit tests only (the default)       |
| `uv run pytest -m itunes`   | iTunes integration tests only       |
| `uv run pytest -m ""`       | All tests                           |

**Formatting and imports**

[Ruff](https://docs.astral.sh/ruff/) formats code and optimizes imports (sorts them and removes
unused ones), configured in `pyproject.toml` to follow PyCharm's defaults with 120-column lines.
To make PyCharm's own *Reformat Code* agree with Ruff, enable Ruff under
**Settings → Python → Tools → Ruff**.

| Command                                | Does                                          |
|----------------------------------------|-----------------------------------------------|
| `uv run ruff format .`                 | Format all files                              |
| `uv run ruff check --fix .`            | Sort imports and remove unused ones           |
| `uv run ruff format --check --diff .`  | Show formatting problems without fixing them  |
| `uv run ruff check .`                  | Show import problems without fixing them      |
| `uv run pre-commit run --all-files`    | Run the commit hooks on every tracked file    |
