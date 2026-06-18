import threading
import time

from panel.app import app

BROWSE_WATCHDOG_INTERVAL_S = 8.0


def _run_flask():
    app.run(host="127.0.0.1", port=8765, threaded=True, use_reloader=False)


def _browse_watchdog_tick() -> bool:
    """看門狗單次檢查：若『網站瀏覽』啟用且專用 Chrome 沒在跑（例如被使用者誤關）→ 重開。
    讀即時 .env 狀態（非 import 時的 config），避免使用者剛關掉開關時又被拉起來。回是否觸發重開。"""
    try:
        import browse_launch
        from panel import env_io
        if env_io.read_browse_enabled() and not browse_launch.cdp_alive():
            browse_launch.launch(headless=browse_launch.desired_headless())
            return True
    except Exception:
        pass
    return False


def _browse_watchdog_loop(interval: float = BROWSE_WATCHDOG_INTERVAL_S):
    while True:
        time.sleep(interval)            # 啟動時的首次拉起交給 launch_if_enabled，這裡只負責持續守護
        _browse_watchdog_tick()


def main():
    import webview
    import browse_launch
    threading.Thread(target=_run_flask, daemon=True).start()
    # 啟用瀏覽就在背景拉起專用 Chrome（重放開關狀態）→ 重開/重啟後不必再手動切開關
    threading.Thread(target=browse_launch.launch_if_enabled, daemon=True).start()
    # 看門狗：啟用期間若專用瀏覽器被誤關，幾秒內自動重開（面板程序 launch，無 greenlet 問題）
    threading.Thread(target=_browse_watchdog_loop, daemon=True).start()
    webview.create_window("JAYVIS · 控制台", "http://127.0.0.1:8765",
                          width=920, height=820)
    webview.start()


if __name__ == "__main__":
    main()
