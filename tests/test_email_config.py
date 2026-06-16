import importlib

import pytest

import config


@pytest.fixture(autouse=True)
def _restore():
    yield
    importlib.reload(config)


def test_email_defaults(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("MAIL_ACCOUNT", "")
    importlib.reload(config)
    assert config.EMAIL_ENABLED is False
    assert config.MAIL_ACCOUNT == ""


def test_email_enabled(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("MAIL_ACCOUNT", "me@x.com")
    importlib.reload(config)
    assert config.EMAIL_ENABLED is True
    assert config.MAIL_ACCOUNT == "me@x.com"
