import json
import config
import browse_agent as bag
import browse_tool as bt


def _mock_browser(monkeypatch, snap=None, clicks=None):
    snap = snap if snap is not None else []
    monkeypatch.setattr(bt, "connect", lambda: None)
    monkeypatch.setattr(bt, "goto", lambda url: None)
    monkeypatch.setattr(bt, "current_url", lambda: "https://example.com/")
    monkeypatch.setattr(bt, "snapshot", lambda: snap)
    monkeypatch.setattr(bt, "extract_text", lambda: "頁面文字")
    monkeypatch.setattr(bt, "screenshot", lambda: b"PNG")
    monkeypatch.setattr(bt, "type_text", lambda ref, text: None)
    if clicks is not None:
        monkeypatch.setattr(bt, "click", lambda ref: clicks.append(ref))
    else:
        monkeypatch.setattr(bt, "click", lambda ref: None)


def _decides(monkeypatch, *jsons):
    seq = list(jsons)
    def fake(**k):
        return seq.pop(0)
    monkeypatch.setattr(bag, "generate", fake)


def test_read_path_returns_ok_summary(monkeypatch):
    _mock_browser(monkeypatch)
    _decides(monkeypatch, json.dumps({"action": "done", "summary": "本週流量 12000", "mutating": False}))
    res = bag.run("看本週流量")
    assert res.status == "ok"
    assert "12000" in res.summary
    assert res.screenshot == b"PNG"


def test_mutating_action_returns_pending_without_executing(monkeypatch):
    clicks = []
    _mock_browser(monkeypatch, snap=[{"ref": 2, "tag": "button", "name": "發布貼文"}], clicks=clicks)
    _decides(monkeypatch, json.dumps({"action": "click", "ref": 2, "mutating": True, "why": "發布貼文"}))
    res = bag.run("把這篇發布")
    assert res.status == "pending"
    assert res.pending["ref"] == 2
    assert clicks == []                       # 關鍵：未執行點擊


def test_mutating_detected_by_name_even_if_model_says_false(monkeypatch):
    clicks = []
    _mock_browser(monkeypatch, snap=[{"ref": 0, "tag": "button", "name": "刪除"}], clicks=clicks)
    _decides(monkeypatch, json.dumps({"action": "click", "ref": 0, "mutating": False, "why": "x"}))
    res = bag.run("處理一下")
    assert res.status == "pending"            # 名稱命中 MUTATING_HINT → 仍視為寫入
    assert clicks == []


def test_resume_approved_executes_action(monkeypatch):
    clicks = []
    _mock_browser(monkeypatch, clicks=clicks)
    res = bag.resume({"action": "click", "ref": 5}, approved=True)
    assert res.status == "ok"
    assert clicks == [5]


def test_resume_cancel_does_not_execute(monkeypatch):
    clicks = []
    _mock_browser(monkeypatch, clicks=clicks)
    res = bag.resume({"action": "click", "ref": 5}, approved=False)
    assert res.status == "ok"
    assert clicks == []
    assert "取消" in res.summary


def test_step_cap_returns_ok(monkeypatch):
    monkeypatch.setattr(config, "BROWSE_MAX_STEPS", 2)
    _mock_browser(monkeypatch)
    # 永遠回非 done、非 mutating 的 read → 迴圈耗盡
    _decides(monkeypatch,
             json.dumps({"action": "read", "mutating": False}),
             json.dumps({"action": "read", "mutating": False}))
    res = bag.run("無止盡")
    assert res.status == "ok"
    assert "步驟" in res.summary
