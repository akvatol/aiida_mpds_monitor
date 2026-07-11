
import os
from pathlib import Path

import yaml
from aiida.common.extendeddicts import AttributeDict


DEFAULT_CONFIG_PATH = Path.home() / ".aiida" / "aiida_mpds_monitor" / "conf.yaml"

DEFAULT_CONFIG = {
    "webhook_url": "http://localhost:8080",
    "auth_key": "",
    "poll_interval": 30,
    "workchain_hierarchy": {
        "MPDSStructureWorkChain": {
            "BaseCrystalWorkChain": ["CrystalParallelCalculation"]
        }
    },
    "log_file": "/data/aiida_mpds_monitor.log",
    "log_level": "WARNING",  # INFO, DEBUG, WARNING, ERROR
    "log_max_bytes": 10 * 1024 * 1024,  # 10 MB
    "log_backup_count": 3,
    "archive_upload_url": "",
    "archive_keep": False,
    "archive_key": "",
    "send_archive": True,
}


def ensure_config_dir():
    config_dir = DEFAULT_CONFIG_PATH.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config_dir, 0o755)
    return DEFAULT_CONFIG_PATH


def load_config():
    config_path = ensure_config_dir()

    if not config_path.exists():
        print(f"Creating default config at {config_path}")
        with open(config_path, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        config_path.chmod(0o644)

    with open(config_path) as f:
        user_config = yaml.safe_load(f) or {}

    # Merging user config with defaults
    final_config = {**DEFAULT_CONFIG, **user_config}
    return AttributeDict(final_config)


def get_auth_key():
    return os.environ.get("MPDS_MONITOR_KEY", "")


def get_archive_key():
    return os.environ.get("MPDS_ARCHIVE_KEY") or get_auth_key()


def resolve_archive_upload_url():
    return os.environ.get("ARCHIVE_UPLOAD_URL", "https://esdd.io/api/v1/tasks/upload/absolidix")
