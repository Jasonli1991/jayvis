import config


def test_browse_defaults():
    assert config.BROWSE_ENABLED is False           # 預設關
    assert config.BROWSE_CDP_URL == "http://localhost:9222"
    assert config.BROWSE_MAX_STEPS == 12
    assert config.BROWSE_MODEL == "claude-opus-4-8"
    assert config.BROWSE_NAV_TIMEOUT_S == 30
    assert config.BROWSE_TMP_DIR.endswith("browse_tmp")
