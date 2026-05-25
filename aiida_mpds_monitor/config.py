
import os
from pathlib import Path

import yaml
from aiida.common.extendeddicts import AttributeDict


DEFAULT_CONFIG_PATH = Path("/etc/aiida_mpds_monitor/conf.yaml")

DEFAULT_CONFIG = {
    "webhook_url": "http://localhost:8080",
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
}


def ensure_config_dir():
    config_dir = DEFAULT_CONFIG_PATH.parent
    if not config_dir.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(config_dir, 0o755)
        except PermissionError:
            fallback = Path.home() / ".config/aiida_mpds_monitor/conf.yaml"
            return fallback
    return DEFAULT_CONFIG_PATH


def load_config():
    config_path = ensure_config_dir()

    if not config_path.exists():
        print(f"Creating default config at {config_path}")
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            config_path.chmod(0o644)
        except PermissionError:
            fallback = Path.home() / ".config/aiida_mpds_monitor/conf.yaml"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            print(f"Using fallback config: {fallback}")
            with open(fallback, "w") as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            config_path = fallback

    with open(config_path) as f:
        user_config = yaml.safe_load(f) or {}

    # Merging user config with defaults
    final_config = {**DEFAULT_CONFIG, **user_config}
    return AttributeDict(final_config)


def get_auth_key():
    """Get authentication key from MPDS_MONITOR_KEY environment variable.

    Returns:
        str: The authentication key, or empty string if not set
    """
    return os.environ.get("MPDS_MONITOR_KEY", "")


def get_archive_key(config=None):
    """Get the archive upload authentication key.

    Resolution order:
    1. ``MPDS_ARCHIVE_KEY`` environment variable
    2. ``archive_key`` from config
    3. Falls back to ``MPDS_MONITOR_KEY`` (the webhook key) for backward
       compatibility

    Args:
        config: Loaded config object (AttributeDict). Optional.

    Returns:
        str: The archive authentication key, or empty string if none found.
    """
    env_key = os.environ.get("MPDS_ARCHIVE_KEY", "")
    if env_key:
        return env_key
    if config:
        cfg_key = config.get("archive_key", "")
        if cfg_key:
            return cfg_key
    return os.environ.get("MPDS_MONITOR_KEY", "")


def resolve_archive_upload_url(config, logger=None):
    """Resolve the archive upload URL from config.

    Uses ``archive_upload_url`` if set; otherwise falls back to deriving it
    from ``webhook_url`` and logs a deprecation warning.

    Args:
        config: Loaded config object (AttributeDict).
        logger: Optional logger for deprecation warnings.

    Returns:
        str: The resolved upload URL.
    """
    url = config.get("archive_upload_url", "")
    if url:
        return url
    fallback = f"{config.get('webhook_url', '').rstrip('/')}/upload/absolidix"
    if logger:
        logger.warning(
            "archive_upload_url is not set; falling back to derived URL %r. "
            "Set archive_upload_url in conf.yaml to suppress this warning.",
            fallback,
        )
    else:
        import warnings
        warnings.warn(
            f"archive_upload_url is not set; falling back to derived URL {fallback!r}. "
            "Set archive_upload_url in conf.yaml to suppress this warning.",
            DeprecationWarning,
            stacklevel=2,
        )
    return fallback
