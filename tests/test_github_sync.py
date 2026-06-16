import github_sync


def test_status_empty_when_no_repos(monkeypatch):
    """GITHUB_REPOS 留空 → 不該注入空殼標題到 system prompt"""
    monkeypatch.setattr(github_sync, "GITHUB_REPOS", [])
    assert github_sync.get_project_status() == ""


def test_status_lists_sections_when_repos(monkeypatch):
    monkeypatch.setattr(github_sync, "GITHUB_REPOS", ["a/b"])
    monkeypatch.setattr(github_sync, "_fetch_commits",
                        lambda repo: [{"date": "2026-06-01T10:00:00Z", "author": "X", "msg": "fix: m"}])
    s = github_sync.get_project_status()
    assert "a/b" in s and "2026-06-01" in s and "fix: m" in s
