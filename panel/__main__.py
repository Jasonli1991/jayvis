import threading

from panel.app import app


def _run_flask():
    app.run(host="127.0.0.1", port=8765, threaded=True, use_reloader=False)


def main():
    import webview
    import browse_launch
    threading.Thread(target=_run_flask, daemon=True).start()
    # 啟用瀏覽就在背景拉起專用 Chrome（重放開關狀態）→ 重開/重啟後不必再手動切開關
    threading.Thread(target=browse_launch.launch_if_enabled, daemon=True).start()
    webview.create_window("JAYVIS · 控制台", "http://127.0.0.1:8765",
                          width=920, height=820)
    webview.start()


if __name__ == "__main__":
    main()
