"""解除安裝：移除 JAYVIS 安裝的外部元件（模型／Chromium／LibreOffice），可選清除 JAYVIS 資料。

安全原則：
- 只刪「掃描時提供的路徑」——manifest 記過的（保證 JAYVIS 裝的）＋已知的相關候選；任意路徑一律拒絕。
- manifest 裡的＝JAYVIS 真正裝上的（裝前不存在才會記），可安全移除。
- 「legacy 候選」＝磁碟上存在、但不在 manifest（無法確認來源、可能被別的程式共用）→ 交由使用者 opt-in。
- 清資料只刪 ~/.n 內容，但保留 installed.json（卸載清單不能在清資料時被砍）。
- 端點層另外要求「先停止 bot」才允許執行（模型/檔案可能還在使用）。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import config
import install_manifest

# JAYVIS 會用到的本地模型——legacy 掃描只認這幾個，不碰使用者其他 HF 模型
_KNOWN_MODELS = ["BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", "sentence-transformers/all-MiniLM-L6-v2"]


def _dir_size(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        total = 0
        for root, _, files in os.walk(p):           # os.walk 預設不跟隨符號連結的目錄
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if os.path.islink(fp):
                        continue                    # 跳過符號連結（HF 快取 snapshots 指向 blobs，避免重複計）
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _human(n: int) -> str:
    f = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if f < 1024:
            return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


def _legacy_candidates() -> list:
    """磁碟上存在、但不在 manifest 的 JAYVIS 相關元件（來源無法確認、可能被別程式共用）→ 標 legacy=True，走非破壞性碼路。"""
    seen = {it.get("path") for it in install_manifest.items()}
    out = []
    for name in _KNOWN_MODELS:
        d = install_manifest.hf_model_dir(name)
        if d.exists() and str(d) not in seen:
            out.append({"kind": "model", "path": str(d), "name": name, "legacy": True})
    pw = install_manifest.playwright_browsers_dir()                  # 只列實際的 chromium-* 子目錄，絕不列整個共用根
    if pw.exists():
        for sub in sorted(pw.glob("chromium-*")):
            if sub.is_dir() and str(sub) not in seen:
                out.append({"kind": "chromium", "path": str(sub), "method": "playwright", "legacy": True})
    lo = Path("/Applications/LibreOffice.app")
    if lo.exists() and str(lo) not in seen:
        out.append({"kind": "libreoffice", "path": str(lo), "method": "brew-cask", "legacy": True})
    return out


def _data_files() -> list:
    """JAYVIS 自己的資料（~/.n），但排除 installed.json（卸載清單，不在清資料時刪）。"""
    d = Path(config.DATA_DIR)
    if not d.exists():
        return []
    return [c for c in d.iterdir() if c.name != "installed.json"]


def scan() -> dict:
    """回 {tracked, legacy, data}，各帶容量供面板顯示。"""
    tracked = []
    for it in install_manifest.items():
        p = Path(it["path"])
        ex = p.exists()
        sz = _dir_size(p) if ex else 0
        tracked.append({**it, "exists": ex, "size": sz, "size_h": _human(sz) if ex else "—"})
    legacy = []
    for it in _legacy_candidates():
        sz = _dir_size(Path(it["path"]))
        legacy.append({**it, "exists": True, "size": sz, "size_h": _human(sz)})
    files = _data_files()
    data_sz = sum(_dir_size(p) for p in files)
    return {
        "tracked": tracked,
        "legacy": legacy,
        "data": {"path": str(config.DATA_DIR), "size": data_sz, "size_h": _human(data_sz), "count": len(files)},
    }


def _allowed() -> dict:
    """允許刪除的路徑 → 其元資料（含 method）。manifest ＋ legacy 候選，其他一律拒絕。"""
    return {it["path"]: it for it in (install_manifest.items() + _legacy_candidates())}


def _remove_one(it: dict, path: str) -> tuple:
    legacy = it.get("legacy", False)
    method = it.get("method")
    try:
        if method == "brew-cask":
            if legacy:                           # 來源不明（可能使用者自己裝的）→ 絕不 brew uninstall
                return False, "偵測到 LibreOffice，但非 JAYVIS 安裝，為安全不自動移除；如確定要移請自行 brew uninstall --cask libreoffice"
            from panel import libreoffice
            brew = libreoffice.brew_path()
            if not brew:
                return False, "找不到 brew，無法卸載 LibreOffice"
            r = subprocess.run([brew, "uninstall", "--cask", "libreoffice"],
                               capture_output=True, text=True)
            return (r.returncode == 0), ("已透過 brew 移除" if r.returncode == 0 else (r.stderr.strip()[:200] or "brew 卸載失敗"))
        if method == "playwright":
            p = Path(path)
            root = install_manifest.playwright_browsers_dir().resolve()
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if not (rp != root and rp.parent == root):   # 只准動「根的直接子目錄 chromium-<rev>」，絕不刪整個共用根或外部
                return False, "路徑非預期的 chromium 子目錄，為安全不處理"
            if not legacy:                               # JAYVIS 裝的：先 playwright uninstall（用 .links 引用計數，不傷別專案的瀏覽器）
                subprocess.run([sys.executable, "-m", "playwright", "uninstall"], capture_output=True, text=True)
            if rp.exists():
                shutil.rmtree(rp, ignore_errors=True)
            if p.exists():
                return False, "Chromium 殘留未能完全清除（可能被占用）"
            return True, "已移除 Chromium"
        p = Path(path)                           # 其餘（模型快取等）：直接刪該特定目錄/檔
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            try:
                p.unlink()
            except OSError:
                pass
        if p.exists():                           # ignore_errors 會吞錯 → 必須確認真的消失才算成功（否則殘留卻被 forget）
            return False, "部分檔案未能刪除（可能被占用或權限不足）"
        return True, "已刪除"
    except Exception as e:
        return False, str(e)[:200]


def remove(paths: list, clear_data: bool = False) -> dict:
    """移除指定路徑（限掃描提供的）＋可選清資料。回每項結果。"""
    allowed = _allowed()
    results = []
    for path in paths or []:
        if path not in allowed:                  # 安全：拒絕任意路徑
            results.append({"path": path, "ok": False, "msg": "不在允許清單，已略過"})
            continue
        ok, msg = _remove_one(allowed[path], path)
        if ok:
            install_manifest.forget(path)
        results.append({"path": path, "ok": ok, "msg": msg})
    if clear_data:
        import browse_launch
        browse_launch.suspend_watchdog()         # 先暫停看門狗＋收掉面板自己拉起的專屬 Chromium，否則邊刪 chrome-browse-profile 邊被重開 → 半殘/登入遺失
        try:
            try:
                browse_launch.shutdown()
            except Exception:
                pass
            for c in _data_files():
                try:
                    if c.is_dir():
                        shutil.rmtree(c, ignore_errors=True)
                    else:
                        c.unlink(missing_ok=True)
                    ok = not c.exists()
                    results.append({"path": str(c), "ok": ok, "msg": "已清除" if ok else "部分未能刪除（可能被占用）"})
                except Exception as e:
                    results.append({"path": str(c), "ok": False, "msg": str(e)[:200]})
        finally:
            browse_launch.resume_watchdog()
    return {"results": results}
