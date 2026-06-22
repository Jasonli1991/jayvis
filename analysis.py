import os
import re
from datetime import datetime
from pathlib import Path

import config
import inbox_capture
from db.connection import get_conn
from retrieval.hybrid import hybrid_search
from chunks import citation_of
from llm import generate

_SYSTEM = (
    f"你是 {config.OWNER_NAME} 的分析助理。根據提供的『筆記/commit 片段』綜合回答問題，"
    "可做合理推論與彙整，但**必須明確標註依據**，並說明資料不足或不確定之處；"
    "**不要編造超出所給資料的事實**。用繁體中文、結構化（重點條列）。"
)

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
try:
    _CHARTJS = (_VENDOR_DIR / "chart.umd.min.js").read_text(encoding="utf-8")
except Exception:
    _CHARTJS = ""


def _clean_html(raw: str) -> str:
    """剝掉模型可能加的 ```html / ``` 圍欄與前後空白。"""
    s = (raw or "").strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _looks_like_html(s: str) -> bool:
    low = (s or "").lower()
    return "<html" in low or "<body" in low or "<canvas" in low


def _inject_chartjs(html: str) -> str:
    """把內嵌 Chart.js 注入到 <head> 之後（無 <head> 則 <html> 之後；皆無則 prepend）。"""
    tag = f"<script>{_CHARTJS}</script>"
    i = html.lower().find("<head>")
    if i >= 0:
        j = i + len("<head>")
        return html[:j] + tag + html[j:]
    m = re.search(r"<html[^>]*>", html, re.IGNORECASE)
    if m:
        return html[:m.end()] + tag + html[m.end():]
    return tag + html


def _open_conn():
    return get_conn()


def _source_label(c) -> str:
    return citation_of({"source_type": c.source_type, **c.meta})


def analyze(query: str, owner: str = None, model: str = None,
            k: int = 40, max_context: int = 24000) -> dict:
    owner = owner or config.OWNER_KEY
    model = model or config.MODEL_CODE
    conn = _open_conn()
    try:
        cands = hybrid_search(conn, query, owner=owner, out_k=k)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not cands:
        return {"answer": "找不到相關資料，無法分析。", "sources": []}

    blocks, sources, total = [], [], 0
    for c in cands:
        label = _source_label(c)
        piece = f"[{label}]\n{c.raw_text}"
        if total + len(piece) > max_context:
            break
        blocks.append(piece)
        sources.append(label)
        total += len(piece)

    context = "\n\n---\n\n".join(blocks)
    answer = generate(
        model=model,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"分析問題：{query}\n\n可用資料：\n{context}"}],
        max_output_tokens=4096,
    )
    return {"answer": answer, "sources": sources}


_REPORT_SYSTEM = (
    f"你是 {config.OWNER_NAME} 的分析助理。根據提供的『筆記/commit 片段』做一份非常詳盡的分析報告。\n"
    "輸出一份**完整、自包含的 HTML 文件**（從 <!DOCTYPE html> 到 </html>），"
    "不要任何 HTML 以外的文字、不要 markdown 圍欄。\n"
    "內容要求：\n"
    "- 結構清楚（標題、章節、重點），繁體中文，專業排版（內含 <style>）。\n"
    "- 從資料中找出可量化／時間／類別維度，選**合適的圖表類型**（長條/折線/圓餅/雷達等），"
    "用 <canvas> + <script>new Chart(...)</script> 內嵌圖表與資料。\n"
    "- **假設 Chart 這個全域變數已存在，絕對不要自己加 Chart.js 的 <script src>**（系統會注入內嵌版）。\n"
    "- 必須明確標註依據、說明資料不足或不確定之處；**不要編造超出所給資料的事實**。"
)


def _inbox_dir():
    root = (config.OBSIDIAN_PATH or "").strip()
    if not root or not os.path.isdir(root):
        return None
    return os.path.join(root, *inbox_capture.INBOX_SUBPATH)


def _report_filename(query, now) -> str:
    return f"{now.strftime('%Y-%m-%d-%H%M')}-analysis-{inbox_capture._slug(query)}.html"


_last_report = None        # 上一份報告（記憶體）：{"clean_html","stem","version"} 或 None


def _version_filename(stem: str, version: int) -> str:
    return f"{stem}.html" if version == 1 else f"{stem}-v{version}.html"


def generate_report(query: str, model: str = None, now=None) -> dict:
    """撈 KB → 強模型生完整 HTML → 注入內嵌 Chart.js → 存 Inbox(.html)。回 {ok,path,filename} 或 {ok,error}。"""
    now = now or datetime.now()
    model = model or config.MODEL_CODE
    inbox = _inbox_dir()                              # fail-fast：先驗路徑，不可用就別呼叫模型
    if not inbox:
        return {"ok": False, "error": "Obsidian 路徑沒設好或找不到，先去控制台設定，再執行分析 🙏"}
    try:
        os.makedirs(inbox, exist_ok=True)
    except Exception:
        return {"ok": False, "error": "Obsidian Inbox 資料夾建立失敗，請檢查控制台的 vault 路徑 🙏"}

    conn = _open_conn()
    try:
        cands = hybrid_search(conn, query, owner=config.OWNER_KEY, out_k=config.ANALYSIS_REPORT_K)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if not cands:
        return {"ok": False, "error": "找不到相關資料，無法分析。"}

    blocks, total = [], 0
    for c in cands:
        piece = f"[{_source_label(c)}]\n{c.raw_text}"
        if total + len(piece) > config.ANALYSIS_REPORT_MAX_CONTEXT:
            break
        blocks.append(piece)
        total += len(piece)
    context = "\n\n---\n\n".join(blocks)
    user_msg = f"分析問題：{query}\n\n可用資料：\n{context}"

    html = ""
    for _ in range(2):                               # 防破：最多兩次
        raw = generate(model=model, system=_REPORT_SYSTEM,
                       messages=[{"role": "user", "content": user_msg}],
                       max_output_tokens=config.ANALYSIS_REPORT_MAX_TOKENS)
        html = _clean_html(raw)
        if _looks_like_html(html):
            break
    if not _looks_like_html(html):
        return {"ok": False, "error": "報告生成失敗（模型輸出非 HTML），請重試或在面板把「程式」模型換更強的 🙏"}

    global _last_report
    clean = html                                  # 注入 Chart.js 之前的乾淨 HTML（供接續修改餵回模型）
    fname = _report_filename(query, now)
    path = os.path.join(inbox, fname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_inject_chartjs(clean))
    except Exception:
        return {"ok": False, "error": "報告寫檔失敗，請稍後再試 🙏"}
    _last_report = {"clean_html": clean, "stem": fname[:-5], "version": 1}
    return {"ok": True, "path": path, "filename": fname}


_REFINE_SYSTEM = (
    "你會收到一份既有的 HTML 分析報告，以及使用者的修改要求。\n"
    "請依要求修改，輸出**完整、自包含的 HTML 文件**（從 <!DOCTYPE html> 到 </html>），"
    "不要任何 HTML 以外的文字、不要 markdown 圍欄。\n"
    "- 沒被要求改的部分務必保留原樣；圖表沿用 <canvas> + <script>new Chart(...)</script>，"
    "**假設 Chart 這個全域變數已存在、不要自己加 Chart.js 的 <script src>**（系統會注入內嵌版）。\n"
    "- 繁體中文、專業排版。"
)


def refine_report(instruction: str, model: str = None, now=None) -> dict:
    """把上一份報告的乾淨 HTML + 修改指令餵給模型重生，存成新版本。回 {ok,path,filename} 或 {ok,error}。"""
    global _last_report
    now = now or datetime.now()
    model = model or config.MODEL_CODE
    lr = _last_report
    if not lr:
        return {"ok": False, "error": "還沒有可修改的報告，請先執行一次分析 🙏"}
    inbox = _inbox_dir()                              # fail-fast：先驗路徑，不可用就別呼叫模型
    if not inbox:
        return {"ok": False, "error": "Obsidian 路徑沒設好或找不到，先去控制台設定，再執行分析 🙏"}
    try:
        os.makedirs(inbox, exist_ok=True)
    except Exception:
        return {"ok": False, "error": "Obsidian Inbox 資料夾建立失敗，請檢查控制台的 vault 路徑 🙏"}

    user_msg = f"既有報告 HTML：\n{lr['clean_html']}\n\n修改要求：{instruction}"
    html = ""
    for _ in range(2):                               # 防破：最多兩次
        raw = generate(model=model, system=_REFINE_SYSTEM,
                       messages=[{"role": "user", "content": user_msg}],
                       max_output_tokens=config.ANALYSIS_REPORT_MAX_TOKENS)
        html = _clean_html(raw)
        if _looks_like_html(html):
            break
    if not _looks_like_html(html):
        return {"ok": False, "error": "修改生成失敗（模型輸出非 HTML），請重試或在面板把「程式」模型換更強的 🙏"}

    clean = html
    new_version = lr["version"] + 1
    fname = _version_filename(lr["stem"], new_version)
    path = os.path.join(inbox, fname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_inject_chartjs(clean))
    except Exception:
        return {"ok": False, "error": "報告寫檔失敗，請稍後再試 🙏"}
    _last_report = {"clean_html": clean, "stem": lr["stem"], "version": new_version}
    return {"ok": True, "path": path, "filename": fname}
