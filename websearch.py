"""時事搜尋：由 LLM 判斷該不該查並產生查詢字串（取代脆弱的關鍵字清單）+ Tavily REST。

formulate_query 是單一決策點：回查詢字串＝要查、回空字串＝不必查（閒聊/主觀/常識/靜態知識）。
owner-only 由呼叫端把關。
"""
import json
import urllib.request

import config
from llm import generate as _llm_generate

_QUERY_SYS = (
    "你是『要不要上網查、以及查什麼』的判斷器。看使用者的問題（和近期對話脈絡）：\n"
    "- 若需要『即時／會變動／時效性』資訊才答得準（賽事結果、股價匯率、天氣、新聞時事、"
    "最新發布、某事是否發生、近況…），就輸出『一句最適合丟給搜尋引擎的查詢字串』。\n"
    "- 把代名詞/指涉解析清楚（如『剛剛那個』『他』『這場』），補上必要的時間、實體、地點。\n"
    "- 若不需要上網（純閒聊、主觀感受、常識、已知靜態知識、純情緒），就只輸出 NONE。\n"
    "只輸出查詢字串本身或 NONE，不要解釋、不要引號。\n"
    "例：『西班牙世足賽是不是爆冷了？』→ 西班牙 2026 世界盃 最新賽果\n"
    "例：『你即時搜尋不就知道了？』（脈絡在談西班牙世足）→ 西班牙 2026 世界盃 賽果 爆冷\n"
    "例：『被動元件是什麼』→ NONE\n"
    "例：『今天心情有點差』→ NONE"
)


def formulate_query(message: str, context: str = "") -> str:
    """LLM 判斷該不該查並產生查詢字串。回查詢字串＝要查；回空字串＝不必查。
    LLM 失敗 → 回空字串（寧可不查，也不要拿原句亂搜）。"""
    user = (f"近期對話：\n{context}\n\n這則訊息：{message}" if context else (message or ""))
    try:
        raw = _llm_generate(model=config.MODEL_GENERAL, system=_QUERY_SYS,
                            messages=[{"role": "user", "content": user}], max_output_tokens=80)
    except Exception:
        return ""
    q = (raw or "").strip().strip('"').strip()
    return "" if (not q or q.upper() == "NONE") else q


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
