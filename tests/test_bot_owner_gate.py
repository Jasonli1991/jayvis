import config
import bot


def test_is_owner(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 0)
    assert bot.is_owner(123) is False              # 未設＝沒有 owner
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 123)
    assert bot.is_owner(123) is True
    assert bot.is_owner(999) is False


def test_owner_auto_allowed(monkeypatch):
    """owner 免加白名單就能被回應（自己是主人）。"""
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", set())
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    assert bot.is_allowed(6803) is True
    assert bot.is_allowed(999) is False
