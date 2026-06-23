import sqlite3
from pathlib import Path

import config


def get_conn(path: str | None = None) -> sqlite3.Connection:
    db_path = path or config.KB_PATH
    # 確保資料目錄存在：全新環境（尚未跑 backfill）~/.n 可能還沒建，
    # 否則 sqlite 連線會 OperationalError: unable to open database file。
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
