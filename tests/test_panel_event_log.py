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
    monkeypatch.setattr(app_mod.botctl, "restart", lambda: None)       # 不碰真 bot
    monkeypatch.setattr(app_mod.botctl, "is_running", lambda: True)
    app_mod.app.test_client().post("/api/bot/restart",
                                   headers={"Origin": "http://127.0.0.1:8765"})
    assert any("重啟" in e for e in events)


def test_analyze_logs_event(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod.env_io, "read_models", lambda: {"code": "m"})
    monkeypatch.setattr(app_mod.analysis, "analyze",
                        lambda q, model=None: {"answer": "分析結果文字", "sources": ["a", "b"]})
    r = app_mod.app.test_client().post("/api/analyze", json={"query": "幫我分析最近的爬蟲問題"},
                                       headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200
    assert any("分析" in e and "來源" in e for e in events)
