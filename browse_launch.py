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
# 專用瀏覽器一開就停在的說明頁（提醒使用者「請勿關閉」），避免被誤以為誤開而關掉。
_LANDING_URL = (Path(__file__).resolve().parent / "browse_landing.html").as_uri()
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


def launch(headless: bool = True, wait_s: float = 20.0) -> bool:
    """啟動專用 Chromium。預設 headless（無視窗，給 bot 自動化，根治 macOS AppKit/Metal 崩潰）；
    headless=False 開可見視窗供使用者登入網站。已就緒就直接回 True。回傳 CDP 是否就緒。"""
    if cdp_alive():
        return True
    exe = chromium_path()                        # 未安裝會丟例外 → 由呼叫端處理
    args = [exe, f"--remote-debugging-port={_port()}",
            f"--user-data-dir={config.BROWSE_PROFILE_DIR}",
            "--no-first-run", "--no-default-browser-check",
            # 視窗被遮擋/背景時仍持續合成，否則 headed 截圖會卡死（occlusion 節流）
            "--disable-backgrounding-occluded-windows",
            "--disable-features=CalculateNativeWinOcclusion",
            "--disable-renderer-backgrounding",
            # 軟體渲染：避開 macOS Metal（AGXMetalG13X）崩潰；SwiftShader 純 CPU 繪圖、關 GPU 合成
            "--disable-gpu", "--use-gl=angle", "--use-angle=swiftshader",
            "--disable-gpu-compositing",
            # 乾淨重啟：崩潰後重開不跳「還原分頁？」、不被錯誤對話框/無回應監視器中斷
            "--disable-session-crashed-bubble", "--noerrdialogs", "--disable-hang-monitor"]
    if headless:
        args.append("--headless=new")            # 無視窗：bot 自動化用
    else:
        args.append(_LANDING_URL)                # 可見登入視窗：停在登入說明頁
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if cdp_alive():
            return True
        time.sleep(0.5)
    return cdp_alive()


_login_mode = False


def set_login_mode(on: bool) -> None:
    global _login_mode
    _login_mode = bool(on)


def is_login_mode() -> bool:
    return _login_mode


def desired_headless() -> bool:
    """目前該維持哪種模式：登入模式 → headed(False)；否則 headless(True)。看門狗/啟動共用。"""
    return not _login_mode


def begin_login() -> bool:
    """開可見視窗供登入：標記登入模式 → 收掉現有(headless) → 開 headed。回 CDP 是否就緒。"""
    set_login_mode(True)
    shutdown()
    return launch(headless=False)


def end_login() -> bool:
    """登入完成：清除登入模式 → 收掉(headed) → 回 headless。回 CDP 是否就緒。"""
    set_login_mode(False)
    shutdown()
    return launch(headless=True)


def launch_if_enabled() -> bool:
    """面板啟動時用：若 BROWSE_ENABLED 為真就拉起專用 Chromium（重放 toggle ON 的動作），
    讓重開/重啟後不必再手動切開關。缺 playwright/Chromium 等 → 安靜略過、不拋。回是否就緒。"""
    if not config.BROWSE_ENABLED:
        return False
    try:
        return launch()
    except Exception:
        return False


def shutdown() -> None:
    """關閉專用 Chromium。pattern 用完整 profile 路徑（不以 - 開頭，避免 macOS pkill 報錯），
    只殺帶這個 user-data-dir 的程序，不動到個人 Chrome。"""
    subprocess.run(["pkill", "-f", config.BROWSE_PROFILE_DIR], check=False)
