import importlib
import os

import config


def test_media_enabled_true(monkeypatch):
    monkeypatch.setenv("MEDIA_ENABLED", "true")
    importlib.reload(config)
    assert config.MEDIA_ENABLED is True


def test_media_enabled_false(monkeypatch):
    # 顯式設 false：load_dotenv(override=False) 不會覆蓋已存在的 env，
    # 所以這測的是 config 的解析邏輯，不依賴真實 .env 是否定義此鍵。
    monkeypatch.setenv("MEDIA_ENABLED", "false")
    importlib.reload(config)
    assert config.MEDIA_ENABLED is False


def teardown_module(module):
    # 還原 config 成真實 .env 狀態，避免 reload 後的值污染其他測試。
    os.environ.pop("MEDIA_ENABLED", None)
    importlib.reload(config)
