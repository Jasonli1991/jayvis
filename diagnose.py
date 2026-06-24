"""LLM 自我診斷：把錯誤＋近期 log 丟給「本部署自己設定的 LLM」，產出白話的
原因／影響／建議（以設定/操作層面為主，不叫使用者改程式碼），外加「給作者的線索」。

隱私：全程在本機跑、用本機的 LLM、結果只給本機 owner（由 bot.notify_owner_error DM）。
不對外回報、不 phone-home；owner 自行決定要不要把這份轉給作者。
"""
import logging

import config
from llm import generate

_log = logging.getLogger("jayvis")

# 錯誤本身就是「模型／金鑰／額度」問題時，再呼叫模型診斷沒意義也會一起失敗 → 跳過
_MODEL_ERR_HINTS = ("quota", "429", "resource_exhausted", "ratelimit", "rate limit",
                    "api key", "apikey", "unauthorized", "permission denied", "invalid api")

_SYS = (
    "你是 JAYVIS（自架的個人 Telegram AI 搭檔）的技術診斷助手。"
    "根據『錯誤摘要』與『近期 log』，用繁體中文簡潔回覆，分四段：\n"
    "1.【可能原因】白話說明最可能的原因。\n"
    "2.【影響】對使用者的實際影響。\n"
    "3.【建議】以『設定／操作』層面為主（如：填金鑰、開關功能、重啟 bot、安裝元件、檢查路徑）。"
    "若研判是程式 bug，直說『建議把這份回報轉給作者排查』，不要叫使用者自行改程式碼。\n"
    "4.【給作者的線索】一兩句關鍵技術重點。\n"
    "總長約 250 字內、條列清楚。")


def is_model_error(err_summary: str) -> bool:
    s = (err_summary or "").lower()
    return any(h in s for h in _MODEL_ERR_HINTS)


def build_diagnosis(err_summary: str, log_tail: str) -> str:
    """呼叫本部署的 LLM 產出診斷本文。失敗或空 → 回 ''（呼叫端據此略過）。"""
    user = f"錯誤摘要：\n{err_summary}\n\n近期 log（已濾敏感資訊）：\n{(log_tail or '')[:3000]}"
    try:
        out = generate(model=config.MODEL_GENERAL, system=_SYS,
                       messages=[{"role": "user", "content": user}], max_output_tokens=500)
        return (out or "").strip()
    except Exception as e:
        _log.info("🔍 自我診斷失敗（%s）→ 略過", type(e).__name__)
        return ""


def diagnosis_report(err_summary: str, where: str = "") -> str:
    """組出「可直接轉給作者」的診斷回報；無法診斷（模型問題/呼叫失敗）回 ''。"""
    if is_model_error(err_summary):
        return ""                                   # 模型本身有問題，診斷也會失敗
    try:
        from panel import botctl
        log_tail = botctl.tail_log(40, clean=True)  # clean＝已濾 token/噪音、收摺 traceback
    except Exception:
        log_tail = ""
    body = build_diagnosis(err_summary, log_tail)
    if not body:
        return ""
    head = (f"🔍 JAYVIS 自我診斷（可直接轉給作者協助排查）\n"
            f"版本 v{config.APP_VERSION}｜情境：{where or '處理更新'}\n"
            f"錯誤：{err_summary[:200]}\n\n")
    return head + body
