import config
import memory
import panel.app as app_mod
from db.connection import get_conn, apply_schema


def _setup(tmp_path, monkeypatch):
    dbf = str(tmp_path / "kb.sqlite")
    conn = get_conn(dbf); apply_schema(conn); conn.close()
    monkeypatch.setattr(config, "KB_PATH", dbf)        # memory 預設開這個 DB
    return app_mod.app.test_client()


def test_persons_and_timeline(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    memory.append("7", "user", "我下週要去東京出差三天", alias="Eric")
    persons = c.get("/api/memory/persons").get_json()
    assert any(p["person_id"] == "7" for p in persons)
    tl = c.get("/api/memory/timeline?person=7").get_json()
    assert tl and tl[0]["ts"] and "東京" in tl[0]["content"]


def test_clear_person(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    memory.append("7", "user", "我下週要去東京出差三天", alias="Eric")
    r = c.post("/api/memory/clear", json={"person_id": "7"},
               headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403
    assert c.get("/api/memory/timeline?person=7").get_json() == []


def test_persons_resolves_names(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 123456789)
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {1049728855: "Eric"})
    monkeypatch.setattr(config, "TG_BOT_TOKEN", "x")
    app_mod._name_cache.clear()
    monkeypatch.setattr(app_mod, "_tg_get_chat",
                        lambda token, tg_id: {"ok": True, "result": {"first_name": "Mia"}}
                        if tg_id == "6437087604" else {"ok": False})
    memory.append("123456789", "user", "owner 的訊息很長一段", conn=None)   # owner → OWNER_NAME
    memory.append("1049728855", "user", "白名單同事的訊息", conn=None)        # allowlist → Eric
    memory.append("6437087604", "user", "查 getChat 的同事訊息", conn=None)   # getChat → Mia
    memory.append("9999999999", "user", "查不到的同事訊息", conn=None)        # 查不到 → None
    ps = {p["person_id"]: p["alias"] for p in c.get("/api/memory/persons").get_json()}
    assert ps["123456789"] == "Owner"
    assert ps["1049728855"] == "Eric"
    assert ps["6437087604"] == "Mia"
    assert ps["9999999999"] is None        # 前端會退回顯示 ID


def test_profile_get_and_clear(tmp_path, monkeypatch):
    c = _setup(tmp_path, monkeypatch)
    import user_profile
    user_profile.reset()
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 6803)
    user_profile._write("6803", "- 偏好繁中")
    assert "偏好繁中" in c.get("/api/memory/profile").get_json()["profile"]
    r = c.post("/api/memory/profile/clear", json={}, headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403
    assert c.get("/api/memory/profile").get_json()["profile"] == ""
