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


def test_list_repos_includes_org_repos(monkeypatch):
    """個人 0 repo、但所屬組織有 repo → 清單要包含組織 repo（DashU-7UP 情境）"""
    def fake_run(cmd, **k):
        if cmd[:3] == ["gh", "api", "user/orgs"]:
            return _RunOut(0, "DashU-7UP\n")
        if cmd[:3] == ["gh", "repo", "list"]:
            if cmd[3] == "--limit":                 # 個人（沒帶 owner 參數）
                return _RunOut(0, "")
            return _RunOut(0, "DashU-7UP/ka2ka\nDashU-7UP/e2b-demo\n")   # 組織
        return _RunOut(1, "")
    monkeypatch.setattr(github_sync.subprocess, "run", fake_run)
    assert github_sync.list_repos() == ["DashU-7UP/ka2ka", "DashU-7UP/e2b-demo"]


def test_list_repos_dedupes_personal_and_org(monkeypatch):
    """同一 repo 同時出現在個人與組織清單 → 只留一份、保序"""
    def fake_run(cmd, **k):
        if cmd[:3] == ["gh", "api", "user/orgs"]:
            return _RunOut(0, "Org\n")
        if cmd[:3] == ["gh", "repo", "list"]:
            if cmd[3] == "--limit":
                return _RunOut(0, "me/x\n")
            return _RunOut(0, "me/x\nOrg/y\n")
        return _RunOut(1, "")
    monkeypatch.setattr(github_sync.subprocess, "run", fake_run)
    assert github_sync.list_repos() == ["me/x", "Org/y"]
