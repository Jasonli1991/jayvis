import json

import panel.app as app_mod
from panel import env_io

_ORIGIN = {"Origin": "http://127.0.0.1:8765"}


def _client(tmp_path, monkeypatch):
    f = tmp_path / "owner_profile.json"
    f.write_text(json.dumps({"owner_name": "Owner", "company": "Your Company",
                             "projects": [{"name": "projx", "desc": ""}]}, ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(env_io, "PROFILE_PATH", f)
    return app_mod.app.test_client(), f


def test_profile_post_rejects_all_empty(tmp_path, monkeypatch):
    c, f = _client(tmp_path, monkeypatch)
    # 整份空白（assistant_name 是衍生的「 的助理」，不該讓防呆失效）
    payload = {"owner_name": "", "title": "", "company": "", "assistant_name": " 的助理",
               "projects": [], "team": [], "bosses": [], "routing": ""}
    r = c.post("/api/profile", json=payload, headers=_ORIGIN)
    assert r.get_json()["ok"] is False                       # 防呆擋下
    assert json.loads(f.read_text(encoding="utf-8"))["owner_name"] == "Owner"   # 檔案沒被清


def test_profile_post_accepts_real(tmp_path, monkeypatch):
    c, f = _client(tmp_path, monkeypatch)
    r = c.post("/api/profile", json={"owner_name": "Owner", "company": "Your Company"}, headers=_ORIGIN)
    assert r.get_json()["ok"] is True
    assert json.loads(f.read_text(encoding="utf-8"))["owner_name"] == "Owner"


def test_profile_is_empty_ignores_derived_assistant_name():
    assert app_mod._profile_is_empty({"assistant_name": " 的助理", "projects": [], "team": [], "bosses": []}) is True
    assert app_mod._profile_is_empty({"owner_name": "Owner"}) is False
    assert app_mod._profile_is_empty({"projects": [{"name": "x"}]}) is False
