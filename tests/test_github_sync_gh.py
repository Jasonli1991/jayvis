"""github_sync.gh_ready 測試：抓 commit 靠 gh CLI，沒裝/沒登入要給清楚原因（不靜默）。"""
import github_sync


class _R:
    def __init__(self, rc):
        self.returncode = rc


def test_gh_ready_missing_cli(monkeypatch):
    monkeypatch.setattr(github_sync.shutil, "which", lambda name: None)
    ok, why = github_sync.gh_ready()
    assert ok is False and "安裝" in why          # 提示去 brew install


def test_gh_ready_not_logged_in(monkeypatch):
    monkeypatch.setattr(github_sync.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(github_sync.subprocess, "run", lambda *a, **k: _R(1))
    ok, why = github_sync.gh_ready()
    assert ok is False and "登入" in why          # 提示去 gh auth login


def test_gh_ready_ok(monkeypatch):
    monkeypatch.setattr(github_sync.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(github_sync.subprocess, "run", lambda *a, **k: _R(0))
    ok, why = github_sync.gh_ready()
    assert ok is True and why == ""


class _RunOut:
    def __init__(self, rc, out=""):
        self.returncode = rc
        self.stdout = out


def test_list_repos_parses_owner_repo_lines(monkeypatch):
    monkeypatch.setattr(github_sync.subprocess, "run",
                        lambda *a, **k: _RunOut(0, "owner/a\nowner/b\n\n owner/c \n"))
    assert github_sync.list_repos() == ["owner/a", "owner/b", "owner/c"]


def test_list_repos_empty_on_error(monkeypatch):
    monkeypatch.setattr(github_sync.subprocess, "run", lambda *a, **k: _RunOut(1, ""))
    assert github_sync.list_repos() == []
