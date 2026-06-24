"""安裝記帳：只記錄「原本沒有、由 JAYVIS 裝上」的外部元件（模型／Chromium／LibreOffice），
供日後精準卸載——絕不誤刪使用者在用 JAYVIS 前就已存在、或別的程式共用的東西。

記在 ~/.n/installed.json。每筆：
- kind:   'model' | 'chromium' | 'libreoffice'
- path:   實際位置（顯示容量、判斷是否還在；卸載時依 method 處理）
- method: 'brew-cask' | 'playwright' | None（None＝直接刪 path）
- name:   選填（如模型名）

關鍵：只有「安裝前原本沒有」(pre_existed=False) 才記帳，所以清單裡的東西保證是 JAYVIS 裝的。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import config

MANIFEST = Path(config.DATA_DIR) / "installed.json"


def hf_model_dir(name: str) -> Path:
    """HuggingFace hub 快取中某模型的目錄（BAAI/bge-m3 → .../hub/models--BAAI--bge-m3）。
    尊重 HF_HUB_CACHE／HF_HOME，否則用預設 ~/.cache/huggingface/hub。"""
    hub = os.environ.get("HF_HUB_CACHE")
    if not hub:
        home = os.environ.get("HF_HOME")
        hub = os.path.join(home, "hub") if home else os.path.expanduser("~/.cache/huggingface/hub")
    return Path(hub) / ("models--" + name.replace("/", "--"))


def playwright_browsers_dir() -> Path:
    """Playwright 下載瀏覽器的根目錄（含 chromium-*）。尊重 PLAYWRIGHT_BROWSERS_PATH。"""
    p = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if p:
        return Path(p)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _load() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}


def _save(data: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(MANIFEST.parent), suffix=".tmp")   # 原子寫：temp + replace
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, MANIFEST)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def items() -> list:
    return _load().get("items", [])


def record(kind: str, path: str, **extra) -> None:
    """記一筆 JAYVIS 安裝的元件（以 path 去重）。"""
    data = _load()
    its = data.setdefault("items", [])
    if not any(it.get("path") == path for it in its):
        its.append({"kind": kind, "path": path,
                    **{k: v for k, v in extra.items() if v is not None}})
        _save(data)


def record_if_new(kind: str, path: str, pre_existed: bool, **extra) -> None:
    """只有 pre_existed=False（安裝前原本沒有）才記帳——確保清單只含 JAYVIS 真正裝上的。"""
    if not pre_existed:
        record(kind, path, **extra)


def forget(path: str) -> None:
    """移除成功後把該筆從 manifest 拿掉。"""
    data = _load()
    its = data.get("items", [])
    new = [it for it in its if it.get("path") != path]
    if len(new) != len(its):
        data["items"] = new
        _save(data)
