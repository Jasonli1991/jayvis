import importlib
import os

import pytest

import config


@pytest.fixture(autouse=True)
def _restore_config():
    yield
    # 先清掉本檔覆寫過的 env，再 reload：否則 load_dotenv(override=False) 會留下
    # 舊值（如 OWNER_CHAT_ID=123）污染後續測試。
    for k in ("OWNER_CHAT_ID", "ACTIONS_ENABLED", "CALENDAR_NAME"):
        os.environ.pop(k, None)
    importlib.reload(config)          # 還原成真實 .env


def test_action_config_parses_off(monkeypatch):
    # 顯式給值（load_dotenv override=False，不會被 .env 蓋過）
    monkeypatch.setenv("OWNER_CHAT_ID", "0")
    monkeypatch.setenv("ACTIONS_ENABLED", "false")
    monkeypatch.setenv("CALENDAR_NAME", "")
    importlib.reload(config)
    assert config.OWNER_CHAT_ID == 0          # 0＝動作不觸發
    assert config.ACTIONS_ENABLED is False     # 預設關閉
    assert config.CALENDAR_NAME == ""


def test_action_config_parses_on(monkeypatch):
    monkeypatch.setenv("ACTIONS_ENABLED", "true")
    monkeypatch.setenv("OWNER_CHAT_ID", "123")
    importlib.reload(config)
    assert config.ACTIONS_ENABLED is True
    assert config.OWNER_CHAT_ID == 123
