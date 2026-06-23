"""get_conn 的回歸測試。

複現並鎖住的 bug：全新環境（尚未跑 backfill）下 ~/.n 資料目錄不存在，
舊的 get_conn 直接 sqlite3.connect 會在第一個 PRAGMA 拋
`OperationalError: unable to open database file`，讓 panel 一開就噴錯。
修法：get_conn 連線前先 mkdir 父目錄。
"""
from db.connection import get_conn


def test_get_conn_creates_missing_parent_dir(tmp_path):
    db_path = tmp_path / "nonexistent" / "deep" / "kb.sqlite"
    assert not db_path.parent.exists()        # 父目錄一開始不存在（模擬全新 ~/.n）

    conn = get_conn(str(db_path))
    try:
        assert db_path.parent.exists()         # 應自動建出來
        assert db_path.exists()                # DB 檔也建好
        assert conn.execute("SELECT 1").fetchone()[0] == 1   # 連線可用
    finally:
        conn.close()
