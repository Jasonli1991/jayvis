"""啟動／偵測「專用 Chromium」（Playwright 自帶、版本相容的 Chromium，帶遠端偵錯埠）。

為什麼用 Playwright 自帶的 Chromium 而非系統 Chrome：系統 Chrome 會自動更新到很新的版本
（如 149），可能比 Playwright 支援的還新，connect_over_cdp 會因協定不相容而失敗。Playwright
自帶的 Chromium 版本必對得上，部署到任何機器都一致。專用 profile 與個人 Chrome 完全隔離。
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import config

INSTALL_LOG = Path(__file__).resolve().parent / "browse-install.log"
_install_proc = None


def _port() -> int:
    return urlparse(config.BROWSE_CDP_URL).port or 9222


def cdp_alive(timeout: float = 1.0) -> bool:
    """遠端偵錯埠是否已就緒。"""
    url = config.BROWSE_CDP_URL.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def chromium_path() -> str:
    """Playwright 自帶 headed Chromium 的執行檔路徑（未安裝 playwright 套件會丟例外）。"""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        return pw.chromium.executable_path
    finally:
        pw.stop()


def is_ready() -> bool:
    """playwright 套件 + Chromium 二進位是否都就緒（可直接瀏覽）。"""
    try:
        p = chromium_path()
        return bool(p) and os.path.exists(p)
    except Exception:
        return False


def is_installing() -> bool:
    return _install_proc is not None and _install_proc.poll() is None


def install_status() -> dict:
    """供面板輪詢：元件是否就緒、是否正在背景安裝。"""
    return {"ready": is_ready(), "installing": is_installing()}


def start_install() -> dict:
    """背景安裝 playwright 套件 + 下載 Chromium 到「當前 venv」(sys.executable)，非阻塞。
    仿 LibreOffice：Popen 背景跑、寫 log，面板自行輪詢 install_status()。"""
    global _install_proc
    if is_ready():
        return {"ready": True}
    if is_installing():
        return {"installing": True}
    logf = open(INSTALL_LOG, "a")
    # 背景子行程依序跑 pip install + playwright install（list 形式、無 shell，避免注入）
    runner = ("import subprocess, sys;"
              "subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'playwright>=1.40']);"
              "subprocess.check_call([sys.executable, '-m', 'playwright', 'install', 'chromium'])")
    _install_proc = subprocess.Popen([sys.executable, "-c", runner],
                                     stdout=logf, stderr=subprocess.STDOUT)
    return {"installing": True}


def launch(wait_s: float = 20.0) -> bool:
    """啟動專用 Chromium（headed，帶偵錯埠）。已就緒就直接回 True。回傳 CDP 是否就緒。"""
    if cdp_alive():
        return True
    exe = chromium_path()                        # 未安裝會丟例外 → 由呼叫端處理
    subprocess.Popen(
        [exe, f"--remote-debugging-port={_port()}",
         f"--user-data-dir={config.BROWSE_PROFILE_DIR}",
         "--no-first-run", "--no-default-browser-check",
         # 視窗被遮擋/背景時仍持續合成，否則 headed 截圖會卡死（occlusion 節流）
         "--disable-backgrounding-occluded-windows",
         "--disable-features=CalculateNativeWinOcclusion",
         "--disable-renderer-backgrounding",
         # 軟體渲染：避開 macOS Metal GPU 崩潰（自動化瀏覽器更穩，截圖照常）
         "--disable-gpu"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if cdp_alive():
            return True
        time.sleep(0.5)
    return cdp_alive()


def shutdown() -> None:
    """關閉專用 Chromium。pattern 用完整 profile 路徑（不以 - 開頭，避免 macOS pkill 報錯），
    只殺帶這個 user-data-dir 的程序，不動到個人 Chrome。"""
    subprocess.run(["pkill", "-f", config.BROWSE_PROFILE_DIR], check=False)
