from aiida.common.extendeddicts import AttributeDict

from aiida_mpds_monitor.config import get_auth_key


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