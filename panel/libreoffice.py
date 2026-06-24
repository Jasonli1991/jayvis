"""一鍵安裝 LibreOffice（文件轉檔用）：背景跑 brew install --cask，面板輪詢狀態。"""
import os
import shutil
import subprocess
from pathlib import Path

import doc_tool
import install_manifest

_BREW_CANDIDATES = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew", "brew"]
LOG_FILE = Path(__file__).resolve().parent.parent / "libreoffice-install.log"
_APP_PATH = "/Applications/LibreOffice.app"
_proc = None
_started = False        # 本次面板是否啟動過安裝（用來在完成時記帳：只記 JAYVIS 裝的）


def is_installed() -> bool:
    return doc_tool.soffice_path() is not None


def brew_path():
    for c in _BREW_CANDIDATES:
        p = shutil.which(c) if os.path.basename(c) == c else (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def is_installing() -> bool:
    return _proc is not None and _proc.poll() is None


def status() -> dict:
    global _started
    if _started and is_installed() and not is_installing():       # 安裝完成 → 記帳（start_install 只在原本沒裝時才跑，故必為 JAYVIS 裝的）
        try:
            install_manifest.record_if_new("libreoffice", _APP_PATH, pre_existed=False, method="brew-cask")
        except Exception:
            pass
        _started = False
    return {"installed": is_installed(), "installing": is_installing(),
            "has_brew": brew_path() is not None}


def start_install() -> dict:
    """背景啟動 brew 安裝（非阻塞）。回狀態字典供面板輪詢。"""
    global _proc, _started
    if is_installed():
        return {"installed": True}
    if is_installing():
        return {"installing": True}
    brew = brew_path()
    if brew is None:
        return {"error": "no_brew"}
    logf = open(LOG_FILE, "a")
    _proc = subprocess.Popen([brew, "install", "--cask", "libreoffice"],
                             stdout=logf, stderr=subprocess.STDOUT)
    _started = True
    return {"started": True}
