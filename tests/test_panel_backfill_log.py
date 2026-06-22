import panel.app as app_mod


class _FakeConn:
    def close(self):
        pass


def test_run_backfill_logs_start_and_result(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod, "get_conn", lambda: _FakeConn())
    monkeypatch.setattr(app_mod, "apply_schema", lambda c: None)
    monkeypatch.setattr(app_mod, "get_key", lambda env, k: "/vault")
    monkeypatch.setattr(app_mod, "ingest_dir", lambda conn, path: 5)
    monkeypatch.setattr(app_mod, "count_md_files", lambda path: 7)
    app_mod._backfill["running"] = True
    app_mod._run_backfill("obsidian")
    assert any("開始" in e for e in events)                  # 開始有進 log
    assert any("寫入 5" in e for e in events)                # 結果有進 log
    assert app_mod._backfill["running"] is False             # 收尾解鎖


def test_run_backfill_logs_failure(monkeypatch):
    events = []
    monkeypatch.setattr(app_mod.botctl, "log_event", lambda m: events.append(m))
    monkeypatch.setattr(app_mod, "get_conn", lambda: (_ for _ in ()).throw(RuntimeError("db boom")))
    app_mod._backfill["running"] = True
    app_mod._run_backfill("obsidian")
    assert any("失敗" in e for e in events)
    assert app_mod._backfill["running"] is False
