import pytest

from panel import env_io
from panel.app import app


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """隔離 .env：即使防護失效（紅燈階段），測試也絕不能寫到真實設定檔。"""
    envf = tmp_path / ".env"
    envf.write_text("", encoding="utf-8")
    monkeypatch.setattr(env_io, "ENV_PATH", str(envf))


def test_cross_origin_post_blocked():
    """惡意網頁對 localhost 的 CSRF：跨來源 POST 一律 403。"""
    r = app.test_client().post("/api/llm-keys", json={"openai": "evil"},
                               headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_same_origin_post_allowed(monkeypatch):
    # mock botctl：只驗證同源 POST 不被擋，絕不真的重啟正式 bot（測試不可干擾 live 行程）
    import panel.app as app_mod
    monkeypatch.setattr(app_mod.botctl, "restart", lambda: None)
    monkeypatch.setattr(app_mod.botctl, "is_running", lambda: True)
    r = app.test_client().post("/api/bot/restart",
                               headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403


def test_no_origin_post_allowed():
    """本機工具（curl / pywebview 某些情境）不帶 Origin → 放行。"""
    r = app.test_client().get("/api/llm-keys")
    assert r.status_code == 200


def test_dns_rebinding_host_blocked():
    """DNS rebinding：Host 非本機 → 403（所有方法）。"""
    r = app.test_client().get("/api/status", headers={"Host": "evil.example:8765"})
    assert r.status_code == 403


def test_cross_origin_get_blocked():
    """跨來源 GET 也擋：惡意網站不能驅動憑證型端點（如 verify-tg-id 用 bot token）。"""
    r = app.test_client().get("/api/verify-tg-id?id=123456",
                              headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
