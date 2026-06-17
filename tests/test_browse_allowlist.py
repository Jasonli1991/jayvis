import json
import browse_allowlist as ba


def _point(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "_PATH", tmp_path / "browse_allowlist.json")


def test_empty_is_fail_closed(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    assert ba.load() == []
    assert ba.is_allowed("https://anything.com/x") is False   # 空白名單＝全拒


def test_exact_and_subdomain_match(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    ba.save(["example.com", "analytics.google.com"])
    assert ba.is_allowed("https://example.com/a") is True
    assert ba.is_allowed("https://www.example.com/a") is True     # 子網域
    assert ba.is_allowed("https://analytics.google.com/") is True
    assert ba.is_allowed("https://evil.com/") is False
    assert ba.is_allowed("https://notexample.com/") is False      # 不是後綴誤判


def test_add_remove_roundtrip(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    ba.add("a.com")
    ba.add("a.com")                       # 去重
    ba.add("b.com")
    assert sorted(ba.load()) == ["a.com", "b.com"]
    ba.remove("a.com")
    assert ba.load() == ["b.com"]
    # 落地檔內容正確
    assert json.loads((tmp_path / "browse_allowlist.json").read_text())["domains"] == ["b.com"]


def test_save_normalizes(tmp_path, monkeypatch):
    _point(tmp_path, monkeypatch)
    ba.save([" Example.com ", "example.com", ""])   # 去空白/小寫/去重/去空
    assert ba.load() == ["example.com"]
