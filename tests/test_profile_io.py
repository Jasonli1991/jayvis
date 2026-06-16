import json

from panel import env_io


def test_profile_round_trip(tmp_path, monkeypatch):
    f = tmp_path / "owner_profile.json"
    f.write_text(json.dumps({"owner_name": "Amy", "projects": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(env_io, "PROFILE_PATH", f)
    d = env_io.read_profile()
    assert d["owner_name"] == "Amy"
    d["owner_name"] = "Bob"
    env_io.write_profile(d)
    assert json.loads(f.read_text(encoding="utf-8"))["owner_name"] == "Bob"


from panel import env_io as _eio


def test_is_on_leave(monkeypatch):
    monkeypatch.setattr(_eio, "read_leave",
                        lambda: {"status": "請假中（2026-06-16 ~ 2026-06-20，預計 2026-06-21 回來）"})
    assert _eio.is_on_leave() is True
    monkeypatch.setattr(_eio, "read_leave", lambda: {"status": "在職中（目前無排定請假）"})
    assert _eio.is_on_leave() is False


def test_sources_code_root_round_trip(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(_eio, "ENV_PATH", envf)
    _eio.write_sources("/vault", ["owner/repo"], "/Users/x/MyProjects")
    s = _eio.read_sources()
    assert s["code_root"] == "/Users/x/MyProjects"
    assert s["obsidian_path"] == "/vault"
