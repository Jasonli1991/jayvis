import config


def test_browse_defaults():
    # BROWSE_ENABLED 由使用者 .env 決定（面板開關會寫入），這裡只驗型別不寫死值。
    assert isinstance(config.BROWSE_ENABLED, bool)
    assert config.BROWSE_CDP_URL == "http://localhost:9222"
    assert config.BROWSE_MAX_STEPS == 12
    assert config.BROWSE_MODEL == "claude-opus-4-8"
    assert config.BROWSE_NAV_TIMEOUT_S == 30
    assert config.BROWSE_TMP_DIR.endswith("browse_tmp")


def test_browse_enabled_parses_truthy(monkeypatch):
    # 解析邏輯：true/1/yes/on 皆為 True；其餘 False（與面板寫的 "true" 對齊）。
    import importlib
    for val, expect in [("true", True), ("1", True), ("YES", True), ("on", True),
                        ("false", False), ("0", False), ("", False)]:
        monkeypatch.setenv("BROWSE_ENABLED", val)
        assert importlib.reload(config).BROWSE_ENABLED is expect
    monkeypatch.delenv("BROWSE_ENABLED", raising=False)
    importlib.reload(config)
