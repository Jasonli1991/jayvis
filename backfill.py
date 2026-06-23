import asyncio
from dotenv import load_dotenv
load_dotenv()

from db.connection import get_conn, apply_schema
from ingest.obsidian import ingest_obsidian
from ingest.github import commit_to_chunk
from github_sync import _fetch_commits
from config import GITHUB_REPOS


def backfill_obsidian(conn) -> int:
    return ingest_obsidian(conn)


def backfill_github(conn) -> int:
    n = 0
    for repo in GITHUB_REPOS:
        for c in _fetch_commits(repo):
            rec = commit_to_chunk(conn, repo=repo, sha=c.get("sha", c.get("date", "")[:8]),
                                  author=c.get("author", ""), date=c.get("date", "")[:10],
                                  msg=c.get("msg", ""))
            if rec.raw_text:
                n += 1
    return n


def main():
    conn = get_conn()
    apply_schema(conn)
    print("Obsidian:", backfill_obsidian(conn), "chunks")
    print("GitHub:", backfill_github(conn), "chunks")


if __name__ == "__main__":
    main()
