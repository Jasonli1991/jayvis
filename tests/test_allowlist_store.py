import json

import config


def test_load_from_json(tmp_path, monkeypatch):
    f = tmp_path / "allowlist.json"
    f.write_text(json.dumps([{"id": 111, "alias": "Morgan"}, {"id": 222, "alias": ""}]), encoding="utf-8")
    monkeypatch.setattr(config, "ALLOWLIST_PATH", f)
    ids, aliases = config._load_allowlist()
    assert ids == {111, 222}
    assert aliases[111] == "Morgan"


def test_migrate_from_env(tmp_path, monkeypatch):
    f = tmp_path / "allowlist.json"        # 不存在 → 觸發遷移
    monkeypatch.setattr(config, "ALLOWLIST_PATH", f)
    monkeypatch.setenv("ALLOWLIST_USER_IDS", "333,444")
    ids, aliases = config._load_allowlist()
    assert ids == {333, 444}
    assert f.exists()                       # 遷移後建檔
    assert {e["id"] for e in json.loads(f.read_text())} == {333, 444}
