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
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    # 既有資料庫的增欄遷移（SQLite 無 ADD COLUMN IF NOT EXISTS）：冪等、可重複跑。
    cols = {row[1] for row in conn.execute("PRAGMA table_info(person_profiles)").fetchall()}
    if "portrait" not in cols:
        conn.execute("ALTER TABLE person_profiles ADD COLUMN portrait TEXT NOT NULL DEFAULT ''")
