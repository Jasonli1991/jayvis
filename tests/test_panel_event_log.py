import panel.app as app_mod
from panel import botctl


def test_log_event_appends_to_bot_log(tmp_path, monkeypatch):
    logf = tmp_path / "bot.log"
    monkeypatch.setattr(botctl, "LOG_FILE", logf)
    botctl.log_event("🔄 控制台重啟 bot")
    assert "🔄 控制台重啟 bot" in logf.read_text(encoding="utf-8")


def test_bot_action_logs_event(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.botctl, "preflight_errors", lambda *a, **k: [])  # pre-flight 放行
    monkeypatch.setattr(app_mod.botctl, "restart", lambda: None)       # 不碰真 bot
    monkeypatch.setattr(app_mod.botctl, "is_running", lambda: True)
    app_mod.app.test_client().post("/api/bot/restart",
                                   headers={"Origin": "http://127.0.0.1:8765"})
    assert any("重啟" in e for e in events)


def test_bot_start_blocked_by_preflight(monkeypatch):
    events, started = [], []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.botctl, "preflight_errors", lambda *a, **k: ["缺 Telegram Bot Token"])
    monkeypatch.setattr(app_mod.botctl, "start", lambda: started.append(True))
    monkeypatch.setattr(app_mod.botctl, "is_running", lambda: False)
    r = app_mod.app.test_client().post("/api/bot/start",
                                       headers={"Origin": "http://127.0.0.1:8765"})
    j = r.get_json()
    assert j["ok"] is False and j["problems"]      # 回問題清單給前端
    assert started == []                           # 缺設定就不真的啟動
    assert any("啟動被擋" in e for e in events)      # 仍記錄事件


def test_analyze_logs_event(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.env_io, "read_models", lambda: {"code": "m"})
    monkeypatch.setattr(app_mod.analysis, "generate_report",
                        lambda q, model=None: {"ok": True, "path": "/x/r.html", "filename": "2026-analysis-x.html"})
    monkeypatch.setattr(app_mod.webbrowser, "open", lambda u: None)
    r = app_mod.app.test_client().post("/api/analyze", json={"query": "幫我分析最近的爬蟲問題"},
                                       headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200
    assert any("分析報告" in e for e in events)


def _hdr():
    return {"Origin": "http://127.0.0.1:8765"}


def test_actions_save_logs_toggles(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.env_io, "write_actions", lambda *a, **k: None)
    app_mod.app.test_client().post(
        "/api/actions",
        json={"enabled": True, "email_enabled": False, "media_enabled": True, "search_enabled": False},
        headers=_hdr())
    assert any("動作工具" in e and "行事曆 ON" in e and "收發信 OFF" in e for e in events)


def test_memory_clear_logs_target(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.memory, "clear", lambda pid: None)
    app_mod.app.test_client().post("/api/memory/clear", json={"person_id": "12345"}, headers=_hdr())
    assert any("清除對談記憶" in e and "12345" in e for e in events)


def test_llm_keys_logs_providers_not_secret(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.env_io, "write_llm_keys", lambda keys: None)
    app_mod.app.test_client().post("/api/llm-keys", json={"gemini": "SECRET-XYZ", "openai": ""}, headers=_hdr())
    joined = " ".join(events)
    assert "gemini" in joined and "SECRET-XYZ" not in joined   # 記供應商、不記金鑰值
    assert "openai" not in joined                              # 空的不記


def test_bot_token_logs_event_not_value(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.env_io, "write_bot_token", lambda t: None)
    app_mod.app.test_client().post("/api/bot-token", json={"token": "123:SECRET"}, headers=_hdr())
    joined = " ".join(events)
    assert "Bot Token" in joined and "SECRET" not in joined    # 只記事件、不記 token 值
