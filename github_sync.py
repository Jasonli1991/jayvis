import subprocess
import json
from datetime import datetime
from config import GITHUB_REPOS, COMMITS_PER_REPO


def _fetch_commits(repo: str) -> list[dict]:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits", "--jq",
             f".[:{COMMITS_PER_REPO}] | .[] | {{sha: .sha[:8], date: .commit.author.date, author: .commit.author.name, msg: (.commit.message | split(\"\\n\")[0])}}"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return []
        return [json.loads(line) for line in result.stdout.strip().splitlines() if line]
    except Exception:
        return []


def get_project_status() -> str:
    """
    抓取所有追蹤 repo 的最新 commit，
    格式化成一段給 LLM 讀的專案現況摘要。
    沒追蹤任何 repo 時回空字串（assistant 會整段跳過，不浪費 prompt）。
    """
    if not GITHUB_REPOS:
        return ""

    sections = []

    for repo in GITHUB_REPOS:
        commits = _fetch_commits(repo)
        if not commits:
            sections.append(f"### {repo}\n（無法取得 commit 紀錄）")
            continue

        lines = []
        for c in commits:
            date = c.get("date", "")[:10]
            author = c.get("author", "")
            msg = c.get("msg", "")
            lines.append(f"- {date} [{author}] {msg}")

        sections.append(f"### {repo}\n" + "\n".join(lines))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"## 各專案最新 Commit（截至 {timestamp}）\n"
    return header + "\n\n".join(sections)


if __name__ == "__main__":
    print(get_project_status())
