import json

import persona


def _profile(tmp_path):
    p = {
        "owner_name": "Amy", "assistant_name": "Amy 的助理", "owner_key": "amy",
        "title": "後端工程師", "company": "ACME",
        "projects": [{"name": "proj1", "desc": "說明一"}],
        "team": [{"name": "Bob", "role": "前端"}],
        "bosses": [{"name": "Carol", "note": "老闆要禮貌"}],
        "routing": "前端 → Bob",
    }
    f = tmp_path / "owner_profile.json"
    f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return f


def test_render_substitutes_owner_name(tmp_path, monkeypatch):
    pf = _profile(tmp_path)
    tmpl = tmp_path / "persona_template.md"
    tmpl.write_text("我是 {{owner_name}} 的助理。\n## 身份\n{{identity}}\n轉介：{{routing}}", encoding="utf-8")
    monkeypatch.setattr(persona, "PROFILE_PATH", pf)
    monkeypatch.setattr(persona, "TEMPLATE_PATH", tmpl)
    out = persona.render_persona()
    assert "Amy" in out
    assert "{{owner_name}}" not in out          # 佔位都被替換
    assert "proj1" in out and "Bob" in out and "Carol" in out  # identity 注入
    assert "前端 → Bob" in out


def test_render_identity_lists_projects_and_team(tmp_path, monkeypatch):
    pf = _profile(tmp_path)
    tmpl = tmp_path / "persona_template.md"
    tmpl.write_text("{{identity}}", encoding="utf-8")
    monkeypatch.setattr(persona, "PROFILE_PATH", pf)
    monkeypatch.setattr(persona, "TEMPLATE_PATH", tmpl)
    out = persona.render_persona()
    assert "後端工程師" in out and "ACME" in out
    assert "說明一" in out and "前端" in out
