from ingest.chat import write_chat_chunk
from ingest.github import commit_to_chunk
from chunks import upsert_chunk


def test_chat_chunk_has_channel_and_type(conn):
    rec = write_chat_chunk(conn, channel="Team Group", idx=0,
                           lines=["[06/01 10:00] Max: 部署好了"])
    row = conn.execute("SELECT source_type, channel FROM chunks WHERE id=:id",
                       {"id": rec.id}).fetchone()
    assert row["source_type"] == "chat"
    assert row["channel"] == "Team Group"


def test_github_commit_chunk_has_repo_and_sha(conn):
    rec = commit_to_chunk(conn, repo="owner/repo",
                          sha="abc12345", author="Owner", date="2026-06-01",
                          msg="fix: 修正登入流程")
    row = conn.execute("SELECT source_type, repo, commit_sha FROM chunks WHERE id=:id",
                       {"id": rec.id}).fetchone()
    assert row["source_type"] == "git"
    assert row["repo"] == "owner/repo"
    assert row["commit_sha"] == "abc12345"
