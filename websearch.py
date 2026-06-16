"""時事搜尋：關鍵詞判斷 + Tavily REST（urllib，無新依賴）。owner-only 由呼叫端把關。"""
import json
import urllib.request

import config

_HINTS = ("最新", "今天", "今日", "現在", "目前", "時事", "新聞", "股價", "股市",
          "匯率", "油價", "天氣", "氣溫", "賽事", "比分", "誰贏", "剛剛", "最近",
          "發生", "上市", "漲跌", "即時")


def looks_like_current_events(text: str) -> bool:
    t = text or ""
    return any(h in t for h in _HINTS)


def search(query: str, n: int = 5):
    """打 Tavily /search。
    回 list[{title,url,content}] = 成功（可能為 []＝查無）；
    回 None = 搜尋失敗（無 key／額度用完／逾時／HTTP 錯誤等）→ 呼叫端據此明確告知。"""
    key = config.TAVILY_API_KEY
    if not key or not (query or "").strip():
        return None
    body = json.dumps({"api_key": key, "query": query, "max_results": n,
                       "include_answer": False, "search_depth": "basic"}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
    except Exception:
        return None
    out = []
    for item in (data.get("results") or [])[:n]:
        out.append({"title": item.get("title", ""), "url": item.get("url", ""),
                    "content": item.get("content", "")})
    return out
