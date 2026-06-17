"""啟動／偵測「專用設定檔」的 Chrome（帶遠端偵錯埠）。純 subprocess + urllib，不依賴 playwright。

專用 profile（config.BROWSE_PROFILE_DIR）是獨立 instance，與個人 Chrome 互不干擾；
第一次需在該視窗手動登入要讓助理瀏覽的網站，cookie 會留在該 profile。
"""
import subprocess
import time
import urllib.request
from urllib.parse import urlparse

import config

_CHROME_APP = "Google Chrome"


def cdp_alive(timeout: float = 1.0) -> bool:
    """遠端偵錯埠是否已就緒（能取得 /json/version）。"""
    url = config.BROWSE_CDP_URL.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def _port() -> int:
    return urlparse(config.BROWSE_CDP_URL).port or 9222


def launch(wait_s: float = 8.0) -> bool:
    """啟動專用 profile 的 Chrome（已就緒就直接回 True）。回傳 CDP 是否就緒。"""
    if cdp_alive():
        return True
    subprocess.run(
        ["open", "-na", _CHROME_APP, "--args",
         f"--remote-debugging-port={_port()}",
         f"--user-data-dir={config.BROWSE_PROFILE_DIR}",
         "--no-first-run", "--no-default-browser-check"],
        check=False,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if cdp_alive():
            return True
        time.sleep(0.5)
    return cdp_alive()


def shutdown() -> None:
    """關閉「專用 profile」的 Chrome。用 user-data-dir 精準比對，不會動到你個人的 Chrome。"""
    subprocess.run(["pkill", "-f", f"--user-data-dir={config.BROWSE_PROFILE_DIR}"], check=False)
