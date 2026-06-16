"""一鍵安裝 LibreOffice（文件轉檔用）：背景跑 brew install --cask，面板輪詢狀態。"""
import os
import shutil
import subprocess
from pathlib import Path

import doc_tool

_BREW_CANDIDATES = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew", "brew"]
LOG_FILE = Path(__file__).resolve().parent.parent / "libreoffice-install.log"
_proc = None


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
    return {"installed": is_installed(), "installing": is_installing(),
            "has_brew": brew_path() is not None}


def start_install() -> dict:
    """背景啟動 brew 安裝（非阻塞）。回狀態字典供面板輪詢。"""
    global _proc
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
    return {"started": True}
