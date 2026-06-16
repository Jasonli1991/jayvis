import config
import bot


def test_is_allowed(monkeypatch):
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {111, 222})
    assert bot.is_allowed(111) is True
    assert bot.is_allowed(999) is False
