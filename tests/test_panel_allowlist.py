import browse_allowlist as ba
from panel.app import app


def test_browse_allowlist_get_post_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "_PATH", tmp_path / "browse_allowlist.json")
    c = app.test_client()

    r = c.get("/api/browse/allowlist")
    assert r.status_code == 200
    assert r.get_json() == {"domains": []}

    r = c.post("/api/browse/allowlist", json={"domains": ["example.com", "example.com"]})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    r = c.get("/api/browse/allowlist")
    assert r.get_json() == {"domains": ["example.com"]}     # 去重後
