"""bot 單一實例鎖（OS flock）回歸測試。

複現問題：start() 只靠單一 .bot.pid 判定是否已在跑，沒有 OS 層級的鎖；
Flask threaded=True 下 /api/bot/{start,stop,restart} 可並發、彼此無互斥 →
競態時兩個 start() 都先通過 is_running() 再各自 spawn，會生出兩隻 bot.py。
兩隻都對同一 token long-poll → telegram.error.Conflict 無限噴，且其中一隻沒被
.bot.pid 追蹤＝孤兒，stop() 永遠殺不到，使用者只好整個關掉面板重開。

修法：bot.py 啟動時取得 flock 排它鎖，拿不到（已有實例持鎖）就自我結束，
從源頭保證同一時間只有一隻在輪詢。鎖隨程序結束自動釋放，不留髒狀態。
"""
import bot


def test_single_instance_lock_blocks_second(tmp_path):
    lp = tmp_path / ".bot.lock"
    ok1, fp1 = bot.acquire_single_instance_lock(lp)
    assert ok1 is True and fp1 is not None            # 第一隻取得鎖

    ok2, fp2 = bot.acquire_single_instance_lock(lp)
    assert ok2 is False and fp2 is None               # 第二隻拿不到 → 應自我結束（不會去輪詢）

    fp1.close()                                        # 第一隻結束 → 鎖釋放
    ok3, fp3 = bot.acquire_single_instance_lock(lp)
    assert ok3 is True                                 # 釋放後可再取得
    fp3.close()


def test_single_instance_lock_independent_files(tmp_path):
    """不同鎖檔互不干擾（確保鎖是綁在指定檔案上）。"""
    a_ok, a_fp = bot.acquire_single_instance_lock(tmp_path / "a.lock")
    b_ok, b_fp = bot.acquire_single_instance_lock(tmp_path / "b.lock")
    assert a_ok and b_ok                               # 兩個不同檔案都能各自上鎖
    a_fp.close()
    b_fp.close()


def test_single_instance_lock_windows_fallback(monkeypatch):
    """模擬 Windows（無 fcntl）：改用 localhost 埠綁定當互斥鎖，第二個實例一樣要被擋下。
    在 macOS 上以 socket 路徑驗證 Windows 替代邏輯（socket 跨平台，可在此機測）。"""
    monkeypatch.setattr(bot, "fcntl", None)
    ok1, h1 = bot.acquire_single_instance_lock()
    assert ok1 is True and h1 is not None              # 第一個綁到埠
    ok2, h2 = bot.acquire_single_instance_lock()
    assert ok2 is False and h2 is None                # 第二個綁不到 → 應自我結束
    h1.close()                                         # 釋放埠
    ok3, h3 = bot.acquire_single_instance_lock()
    assert ok3 is True                                 # 釋放後可再綁
    h3.close()
