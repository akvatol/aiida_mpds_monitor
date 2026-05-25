# aiida-mpds-monitor

A daemon and CLI tool that monitors AiiDA workflows and sends webhooks when configured child workchains complete. Built for the MPDS backend: when a calculation finishes or fails, the tool posts a status payload to a configured endpoint and uploads a `7z` archive of retrieved outputs. The workchain hierarchy and endpoints live in a YAML config file, so you can monitor new workchain types without editing code.

## Installation

```bash
git clone https://github.com/mpds-io/aiida-mpds-monitor.git
cd aiida-mpds-monitor
pip install .
```

## Workflow Label Requirement

> [!IMPORTANT]
> The **label** field on AiiDA workflows determines webhook delivery and server-side processing. The monitor uses it to identify which object the workflow belongs to and which task it solved. Workflows without a label are skipped.
> Give each workflow a descriptive label, e.g. `HgI2/137: Geometry optimization`.

## Configuration

On first run the tool writes a default config file:

- System-wide: `/etc/aiida_mpds_monitor/conf.yaml`
- User fallback: `~/.config/aiida_mpds_monitor/conf.yaml` (used when `/etc` is read-only)

```yaml
webhook_url: "http://localhost:8080"

# Separate endpoint for archive uploads. Leave empty to derive from
# webhook_url + "/upload/absolidix" (deprecated, will log a warning).
archive_upload_url: "http://localhost:8080"

# Keep .7z archives on disk after upload? (default: false — delete on success)
archive_keep: false

poll_interval: 60

workchain_hierarchy:
  MPDSStructureWorkChain:
    BaseCrystalWorkChain:
      - CrystalParallelCalculation

log_file: "/path/to/logs/aiida_mpds_monitor.log"
log_level: "WARNING"          # DEBUG, INFO, WARNING, ERROR
log_max_bytes: 10485760       # 10 MB
log_backup_count: 5
```

## Usage

1. Configure the workchain hierarchy:

```yaml
# conf.yaml
webhook_url: "http://example.com/webhook"
workchain_hierarchy:
  ParentType:
    ChildType:
      - GrandchildType1
```

2. Set the auth key and start the daemon:

```bash
export MPDS_MONITOR_KEY="your-api-key"
aiida-mpds-monitor
```

The daemon:

- Scans for parent workflows matching configured types every `poll_interval` seconds.
- Walks each parent to its children and grandchildren.
- Checks grandchild calculation status.
- Sends a webhook with the status.
- Generates a `.7z` archive and uploads it to `archive_upload_url`.
- Deletes the local archive on successful upload (unless `archive_keep: true`).
- Marks processed parents to avoid duplicates.

Options:

- `--dry-run`: Scan and log, skip sends and marks.
- `--no-commit`: Send webhooks, skip setting AiiDA extras.
- `--resend-all`: Ignore processed flags and send every eligible webhook.
- `--logging-level` / `-l`: Set verbosity (DEBUG through CRITICAL; defaults to ERROR).

`--dry-run` and `--no-commit` are mutually exclusive; `--dry-run` wins.

Examples:

```bash
aiida-mpds-submit 12345                        # default log level (ERROR)
aiida-mpds-submit 12345 --logging-level INFO  # more verbosity
aiida-mpds-monitor --logging-level DEBUG      # debug daemon
```

3. Submit a single parent by hand (useful for backfills or debugging):

```bash
# Send webhooks for all configured children of parent PK=12345
export MPDS_MONITOR_KEY="your-api-key"
aiida-mpds-submit 12345

# Dry-run: see what would be sent (no HTTP request)
aiida-mpds-submit 12345 --dry-run
```

## Testing with Stub Server

Start a local stub that accepts webhooks and prints them:

```bash
aiida-mpds-stub
```

Listens on `http://localhost:8080`.

## Architecture

The system uses hierarchical configuration:

1. **Parent workchains**: top-level workflows to monitor (configurable)
2. **Child workchains**: expected calculations under each parent (configurable)
3. **Grandchild checks**: validation of specific child process types (configurable)

Change the YAML config to monitor any workflow hierarchy without editing code.

## Archive Upload and Cleanup

After sending a webhook, the daemon and CLI build a `.7z` archive and upload it to a separate endpoint.

**`archive_upload_url`** sets the destination for archive uploads. Example curl equivalent:

Leave `archive_upload_url` empty to derive it from `webhook_url + "/upload/absolidix"` (deprecated, produces a warning).

**`archive_keep`** controls local cleanup. Default `false`: delete the `.7z` after a successful upload. Set `true` to keep archives on disk. Failed uploads retain the archive for manual recovery regardless of this setting.

Copyright © 2026 Materials Platform for Data Science OÜ
