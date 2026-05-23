# Project Overview

`aiida-mpds-monitor` is a lightweight Python daemon and CLI toolkit that polls an
[AiiDA](https://www.aiida.net/) profile, watches hierarchical workchains
(parent → child → grandchild), and dispatches webhook notifications when nodes
reach terminal states. It is built for the Materials Platform for Data Science
(MPDS) backend: when a calculation finishes or fails the tool sends a status
payload to a configured endpoint and, on failure, bundles retrieved outputs into
a `7z` archive and uploads it. The hierarchy and endpoint are fully driven by a
YAML config file, so no code changes are needed to monitor new workchain types.

## Repository Structure

```
aiida-mpds-monitor/
├── aiida_mpds_monitor/           # Main package
│   ├── daemon.py                 # Polling loop and node processing
│   ├── submit.py                 # One-shot CLI for manual parent submission
│   ├── config.py                 # YAML config loading and defaults
│   ├── status.py                 # State inspection and child failure checks
│   ├── webhook.py                # HTTP webhook / archive upload sender
│   ├── generate_archive.py       # Builds 7z archives from AiiDA retrieved data
│   ├── stub_server.py            # Local HTTP stub for webhook testing
│   └── __init__.py               # Package init (empty)
├── tests/                        # pytest unit tests (mock-based)
│   ├── test_status.py            # Status logic tests
│   └── test_webhook.py           # Webhook sender tests
├── openspec/                     # Project-specific OpenSpec configuration
│   └── config.yaml
├── .opencode/                    # OpenCode tooling configuration (not app code)
├── build/                        # Build artifacts
├── pyproject.toml                # Package metadata, deps, entry points
├── pytest.ini                    # pytest defaults with coverage
├── uv.lock                       # uv lockfile (reproducible builds)
├── README.md                     # User-facing documentation
└── LICENSE                       # MIT
```

## Build & Development Commands

Install from source (uses `setuptools` backend; `uv.lock` is present for uv
users):

```bash
# Standard pip
pip install -e .

# Or with uv
uv pip install -e .
```

Run the test suite with coverage:

```bash
pytest
```

Start the local webhook stub for manual testing:

```bash
aiida-mpds-stub
```

Run the monitor daemon locally:

```bash
export MPDS_MONITOR_KEY="your-api-key"
aiida-mpds-monitor --logging-level DEBUG
```

Submit a single parent manually:

```bash
export MPDS_MONITOR_KEY="your-api-key"
aiida-mpds-submit 12345 --dry-run
```

> TODO: No formal lint / type-check commands are configured. Consider adding
> `ruff`, `black`, and `mypy` checks.

## Code Style & Conventions

- **Python** target is 3.9+ (per `requires-python`).
- **Naming**: modules are `snake_case`; CLI entry points are `kebab-case`.
- **Formatting**: no enforced formatter is configured; keep lines ≈ 100 chars.
- **Typing**: partial type hints are used (`Optional`, `Path`, `int | None`); new
  code should include annotations.
- **Logging**: use the module-level `logger = logging.getLogger(__name__)`
  pattern; the daemon sets up a `RotatingFileHandler` plus a console handler.
- **Error handling**: prefer defensive try/except blocks that log and return
  `False` / `None` rather than raising in operational code.
- **Commit messages**: repository has no formal template; keep messages concise
  and in present tense.

## Architecture Notes

**Key components**

1. **daemon.py** — main polling loop. Queries `WorkChainNode` objects by
   `process_label`, walks `called` descendants, and delegates status checks and
   delivery. Marks processed parents with an AiiDA extra
   (`webhook_parent_processed`) to avoid duplicates.
2. **status.py** — translates AiiDA process states (`finished`, `running`,
   `excepted`, …) into a small internal vocabulary (`finished`, `excepted`,
   `waiting`). Also inspects the last grandchild calculation to detect child
   failures even when the parent itself reports a clean exit.
3. **webhook.py** — thin `requests` wrapper: `send_webhook` POSTs
   `payload`+`status`+`key`; `send_archive` uploads a `7z` file as
   `multipart/form-data`.
4. **submit.py** — one-shot CLI that reuses the same logic to submit a single
   parent PK without looping.
5. **config.py** — loads `conf.yaml`, merging user values over `DEFAULT_CONFIG`.
   Falls back from `/etc/…` to `~/.config/…` on permission errors.

## Testing Strategy

- **Unit tests** (`pytest`):
  - `tests/test_status.py` — mocked node trees exercising `get_node_status` and
    `check_child_calculation` for success, failure, exception, and custom child
    type scenarios.
  - `tests/test_webhook.py` — mocked `requests.post` verifying success, error,
    timeout, and auth-key inclusion.
- **Coverage**: `pytest-cov` is configured in `pytest.ini` (`--cov=aiida_mpds_monitor`).
- **Manual / integration**: there are no automated integration tests against a
  live AiiDA profile. Use `aiida-mpds-stub` to receive webhooks locally and
  validate end-to-end flow by hand.
- **CI**: > TODO: no GitHub Actions or other CI workflows are present.

## Security & Compliance

- **Secrets**: the auth key is supplied only via the `MPDS_MONITOR_KEY`
  environment variable; it is never committed to source or config files.
- **Webhook payload**: sent as form data (not JSON). The optional `key` field is
  included in the POST body; ensure the endpoint uses TLS in production.
- **Dependency scanning**: > TODO: no automated vulnerability scan (Dependabot,
  Snyx, etc.) is configured.
- **License**: MIT (`LICENSE` at repository root).

## Agent Guardrails

- **Never modify** `.opencode/`, `node_modules/`, `package.json`, or
  `package-lock.json` unless explicitly asked to update OpenCode tooling.
- **Never touch** `uv.lock` by hand; use `uv lock` or `uv pip install` if
  dependencies change.
- **Configuration files** (`conf.yaml`) are user-managed; do not generate or ship
  real endpoint URLs / secrets in templates.
- **AiiDA extras**: the daemon writes `webhook_parent_processed` to nodes.
  Changing the extra key name must be treated as a breaking change.
- **Required review points**: changes to `status.py` logic, webhook schema, or
  archive layout should be double-checked because they affect the remote MPDS
  backend contract.

## Extensibility Hooks

- **`workchain_hierarchy`** in `conf.yaml` — declarative map of parent → child
  → grandchild labels. Adding a new monitored hierarchy requires only a config
  edit.
- **Environment variables**:
  - `MPDS_MONITOR_KEY` — bearer-like auth token sent with every request.
- **Optional archive metadata** in config:
  - `archive_bid` — uploaded as `bid` form field.
  - `archive_schema_id` — uploaded as `schema_id` form field.
- **CLI flags** (no env vars needed):
  - `--dry-run` — scan and log, skip sends and marks.
  - `--no-commit` — send webhooks but skip setting AiiDA extras.
  - `--resend-all` — ignore existing processed flags and re-deliver.
  - `--logging-level` / `-l` — runtime verbosity (`DEBUG` … `CRITICAL`).
- **Logging destinations**: `log_file`, `log_max_bytes`, `log_backup_count` are
  all configurable via YAML.

## Further Reading

- `README.md` — end-user install, config examples, and usage guide.
- `LICENSE` — MIT license text.
- `openspec/config.yaml` — OpenSpec project configuration.
- `pyproject.toml` — dependency specification, classifiers, and console-script
  entry points.

> TODO: no `docs/` directory or ADR documents exist yet.
