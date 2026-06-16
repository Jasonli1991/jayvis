import threading

from panel.app import app


def _run_flask():
    app.run(host="127.0.0.1", port=8765, threaded=True, use_reloader=False)


def main():
    import webview
    threading.Thread(target=_run_flask, daemon=True).start()
    webview.create_window("JAYVIS · 控制台", "http://127.0.0.1:8765",
                          width=920, height=820)
    webview.start()


if __name__ == "__main__":
    main()
