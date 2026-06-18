"""Pollinations.AI 生圖 + 回覆中的隱藏配圖標記解析。"""
import re
import urllib.parse
import urllib.request

import config

# 全形「：」或半形「:」都吃；非貪婪，可跨行
_MARKER_RE = re.compile(r"\[\[圖[:：]\s*(.+?)\]\]", re.S)


def split_marker(text: str):
    """抽出第一個 [[圖：prompt]] 標記。回 (移除所有標記後的乾淨文字, 第一個 prompt 或 None)。"""
    t = text or ""
    m = _MARKER_RE.search(t)
    if not m:
        return t, None
    prompt = (m.group(1) or "").strip()
    clean = _MARKER_RE.sub("", t).strip()
    return clean, (prompt or None)


def generate(prompt: str):
    """打 Pollinations 生圖，回 PNG/JPEG bytes；失敗（無 prompt／逾時／HTTP 錯／空資料）回 None。"""
    if not (prompt or "").strip():
        return None
    url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
           f"?width={config.IMAGE_GEN_SIZE}&height={config.IMAGE_GEN_SIZE}"
           f"&model={config.IMAGE_GEN_MODEL}&nologo=true")
    # 一定要帶 User-Agent：Pollinations 會擋掉 Python urllib 預設 UA 的請求
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JAYVIS)"})
    try:
        with urllib.request.urlopen(req, timeout=config.IMAGE_GEN_TIMEOUT_S) as r:
            data = r.read()
    except Exception:
        return None
    return data if (data and len(data) > 100) else None   # 太小視為非圖
