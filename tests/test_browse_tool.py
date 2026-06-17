import pytest
import browse_tool as bt
import browse_allowlist as ba


def test_goto_blocks_non_whitelisted(monkeypatch):
    monkeypatch.setattr(ba, "is_allowed", lambda url: False)
    with pytest.raises(bt.NotAllowed):
        bt.goto("https://evil.com")        # 白名單擋下，不碰瀏覽器


def test_connect_failure_raises_browse_unavailable(monkeypatch):
    bt.reset()
    monkeypatch.setattr(bt.browse_launch, "launch", lambda *a, **k: False)   # 別真的開 Chrome
    monkeypatch.setattr(bt, "_open_cdp", lambda: (_ for _ in ()).throw(RuntimeError("no chrome")))
    with pytest.raises(bt.BrowseUnavailable):
        bt.connect()


def test_connect_self_heals_after_launch(monkeypatch):
    bt.reset()
    calls = {"open": 0, "launch": 0}

    def fake_open():
        calls["open"] += 1
        if calls["open"] == 1:
            raise RuntimeError("not yet")          # 第一次：專用 Chrome 還沒開
        return ("pw", "browser", "page")           # launch 後重試成功

    monkeypatch.setattr(bt, "_open_cdp", fake_open)
    monkeypatch.setattr(bt.browse_launch, "launch", lambda *a, **k: calls.__setitem__("launch", 1) or True)
    bt.connect()
    assert calls["launch"] == 1                     # 失敗後有嘗試啟動
    assert calls["open"] == 2                       # 重試一次
    assert bt._page == "page"
    bt.reset()


def test_screenshot_returns_bytes(monkeypatch):
    class _Page:
        url = "https://example.com/"
        def screenshot(self, **k):
            return b"PNGDATA"
    monkeypatch.setattr(ba, "is_allowed", lambda url: True)
    monkeypatch.setattr(bt, "_page", _Page())
    assert bt.screenshot() == b"PNGDATA"


def test_screenshot_blocked_when_off_whitelist(monkeypatch):
    class _Page:
        url = "https://evil.com/"
        def screenshot(self, **k):
            raise AssertionError("screenshot() must not be called on blocked domain")
    monkeypatch.setattr(ba, "is_allowed", lambda url: False)
    monkeypatch.setattr(bt, "_page", _Page())
    with pytest.raises(bt.NotAllowed):
        bt.screenshot()


def test_sweep_tmp_removes_files(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "BROWSE_TMP_DIR", str(tmp_path))
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"y")
    bt.sweep_tmp()
    assert list(tmp_path.iterdir()) == []


def test_click_blocked_when_off_whitelist(monkeypatch):
    class _Page:
        url = "https://evil.com/"
        def query_selector_all(self, *a, **k):
            raise AssertionError("must not reach element lookup on blocked domain")
    monkeypatch.setattr(ba, "is_allowed", lambda url: False)
    monkeypatch.setattr(bt, "_page", _Page())
    with pytest.raises(bt.NotAllowed):
        bt.click(0)


def test_type_blocked_when_off_whitelist(monkeypatch):
    class _Page:
        url = "https://evil.com/"
        def query_selector_all(self, *a, **k):
            raise AssertionError("must not reach element lookup on blocked domain")
    monkeypatch.setattr(ba, "is_allowed", lambda url: False)
    monkeypatch.setattr(bt, "_page", _Page())
    with pytest.raises(bt.NotAllowed):
        bt.type_text(0, "x")
