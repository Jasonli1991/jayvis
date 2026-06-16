import doc_tool
from panel import libreoffice
from panel.app import app


def _client():
    return app.test_client()


def test_status_reflects_soffice(monkeypatch):
    monkeypatch.setattr(doc_tool, "soffice_path", lambda: "/Applications/LibreOffice.app/Contents/MacOS/soffice")
    monkeypatch.setattr(libreoffice, "_proc", None)
    j = _client().get("/api/libreoffice").get_json()
    assert j["installed"] is True and j["installing"] is False


def test_install_noop_when_already_installed(monkeypatch):
    monkeypatch.setattr(libreoffice, "is_installed", lambda: True)
    called = {"n": 0}
    monkeypatch.setattr(libreoffice.subprocess, "Popen", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    j = _client().post("/api/libreoffice/install", json={},
                       headers={"Origin": "http://127.0.0.1:8765"}).get_json()
    assert j == {"installed": True} and called["n"] == 0


def test_install_errors_without_brew(monkeypatch):
    monkeypatch.setattr(libreoffice, "is_installed", lambda: False)
    monkeypatch.setattr(libreoffice, "is_installing", lambda: False)
    monkeypatch.setattr(libreoffice, "brew_path", lambda: None)
    j = _client().post("/api/libreoffice/install", json={},
                       headers={"Origin": "http://127.0.0.1:8765"}).get_json()
    assert j == {"error": "no_brew"}


def test_install_starts_in_background(monkeypatch):
    monkeypatch.setattr(libreoffice, "is_installed", lambda: False)
    monkeypatch.setattr(libreoffice, "is_installing", lambda: False)
    monkeypatch.setattr(libreoffice, "brew_path", lambda: "/opt/homebrew/bin/brew")
    seen = {}

    class _FakeProc:
        def poll(self): return None

    def fake_popen(cmd, *a, **k):
        seen["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr(libreoffice.subprocess, "Popen", fake_popen)
    j = _client().post("/api/libreoffice/install", json={},
                       headers={"Origin": "http://127.0.0.1:8765"}).get_json()
    assert j == {"started": True}
    assert seen["cmd"] == ["/opt/homebrew/bin/brew", "install", "--cask", "libreoffice"]
    monkeypatch.setattr(libreoffice, "_proc", None)
