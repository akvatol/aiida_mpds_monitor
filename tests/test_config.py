from aiida.common.extendeddicts import AttributeDict

from aiida_mpds_monitor.config import DEFAULT_CONFIG, get_archive_key, get_auth_key


def test_get_auth_key_from_config(monkeypatch):
    monkeypatch.delenv("MPDS_MONITOR_KEY", raising=False)

    config = AttributeDict({"auth_key": "config-secret"})

    assert get_auth_key(config) == "config-secret"


def test_get_auth_key_env_overrides_config(monkeypatch):
    monkeypatch.setenv("MPDS_MONITOR_KEY", "env-secret")

    config = AttributeDict({"auth_key": "config-secret"})

    assert get_auth_key(config) == "env-secret"


def test_get_auth_key_supports_security_key_alias(monkeypatch):
    monkeypatch.delenv("MPDS_MONITOR_KEY", raising=False)

    config = AttributeDict({"security_key": "legacy-secret"})

    assert get_auth_key(config) == "legacy-secret"


def test_get_auth_key_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MPDS_MONITOR_KEY", raising=False)

    assert get_auth_key(AttributeDict()) is None


def test_archive_key_resolution_order(monkeypatch):
    config = AttributeDict(
        {"auth_key": "webhook-secret", "archive_key": "archive-secret"}
    )

    monkeypatch.setenv("MPDS_MONITOR_KEY", "webhook-env-secret")
    monkeypatch.setenv("MPDS_ARCHIVE_KEY", "archive-env-secret")
    assert get_archive_key(config) == "archive-env-secret"

    monkeypatch.delenv("MPDS_ARCHIVE_KEY")
    assert get_archive_key(config) == "archive-secret"

    config.archive_key = ""
    assert get_archive_key(config) == "webhook-env-secret"


def test_default_filter_configuration_is_disabled():
    assert DEFAULT_CONFIG["monitor_filters"] == {
        "created_after": None,
        "created_before": None,
        "max_age_hours": None,
        "element_counts": [],
        "element_count_greater_than": None,
        "compounds": [],
        "elements": [],
        "elements_match": "any",
    }
