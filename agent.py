"""owner-only 行事曆 agent：JSON-intent 偵測 + 確認狀態機。不灌 RAG。"""
import json
import logging
import sys
from dataclasses import dataclass

import calendar_tool as cal
import config
import doc_tool
import image_tool
import llm
import mail_tool as mail
import memory

_log = logging.getLogger("jayvis")     # 與 bot 同名 → 進同一個 bot.log

_ACTIONS = {"create", "list", "update", "delete",
            "send_email", "list_email", "read_email", "delete_email"}
_EMAIL_ACTIONS = {"send_email", "list_email", "read_email", "delete_email"}
_MEDIA_ACTIONS = {"remove_bg", "convert", "resize"}
# 純文字跟進指令的關鍵字（沒重附圖時，判斷是否要套用到「上一張圖」）。
# 刻意避開會跟行事曆/收信/一般聊天衝突的字（如裸「轉」會誤中「轉介」）。
_MEDIA_HINTS = ("去背", "退底", "去背景", "透明", "轉成", "轉檔", "轉為", "存成",
                "縮到", "縮小", "放大", "尺寸", "解析度", "dpi", "像素", "resize", "裁切", "壓縮")
IS_MACOS = sys.platform == "darwin"   # 行事曆動作靠 AppleScript，僅 macOS
_NOT_MACOS_MSG = "行事曆動作目前僅支援 macOS（用 AppleScript 控制 Calendar）🙏"


def _extract_json(text: str):
    """抽出第一個可解析、含 action 的 JSON 物件（支援巢狀大括號）。"""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def parse_intent(text: str):
    obj = _extract_json(text or "")
    if isinstance(obj, dict) and obj.get("action") in _ACTIONS:
        return obj
    return None


def parse_media_intent(text: str):
    obj = _extract_json(text or "")
    if isinstance(obj, dict) and obj.get("action") in _MEDIA_ACTIONS:
        return obj
    return None


def build_media_system(now) -> str:
    today = now.strftime("%Y-%m-%d")
    return (
        f"今天是 {today}。你是檔案處理助手。使用者已附上一個檔案，並用一句話說要做什麼。\n"
        "只能回傳下列三選一的 JSON（不要多話、不要解釋）：\n"
        '- 去背：{"action":"remove_bg"}\n'
        '- 轉檔：{"action":"convert","to":"pdf"}（to 可為 png/jpg/jpeg/tiff/gif/pdf/docx/xlsx/pptx/txt/html）\n'
        '- 調尺寸或解析度：{"action":"resize","width":1080,"height":null,"longest":null,"percent":null,"dpi":300}\n'
        "  width/height/longest/percent 控像素尺寸（只填使用者提到的，其餘給 null），dpi 控解析度。\n"
        "若使用者的要求不屬於以上三類，回傳 {\"action\":\"none\"}。"
    )


_IMAGE_EXTS = {"png", "jpg", "jpeg", "tif", "tiff", "gif", "bmp", "webp", "heic"}
_IMAGE_TARGETS = {"png", "jpg", "jpeg", "tiff", "gif", "bmp", "pdf"}      # sips 可輸出
_DOC_EXTS = {"doc", "docx", "odt", "rtf", "txt", "html", "xls", "xlsx", "ppt", "pptx", "pdf"}


@dataclass
class MediaResult:
    file: bytes | None = None
    filename: str | None = None
    note: str | None = None          # 附在 caption 的提醒（可選）
    message: str | None = None       # 純文字回覆（澄清/錯誤/額度），file 為 None 時用


def _ext_of(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else "")


def _stem_of(filename: str) -> str:
    return filename.rsplit(".", 1)[0] if "." in (filename or "") else (filename or "file")


def handle_media(text: str, file_bytes: bytes, filename: str, now) -> MediaResult:
    result = _handle_media_impl(text, file_bytes, filename, now)
    if result.file is not None:
        try:
            memory.append(config.OWNER_CHAT_ID, "media",
                          f"處理檔案 {filename} → {result.filename}", alias=config.OWNER_NAME)
        except Exception:
            pass
    return result


def _handle_media_impl(text: str, file_bytes: bytes, filename: str, now) -> MediaResult:
    """owner 傳檔 + 自然語意 → 處理後回 MediaResult。無破壞性，不走確認。"""
    try:
        reply = llm.generate(model=config.MODEL_GENERAL,
                             system=build_media_system(now),
                             messages=[{"role": "user", "content": text or "（無說明）"}],
                             max_output_tokens=256)
    except Exception as e:
        if _is_quota_error(e):
            return MediaResult(message=_QUOTA_MSG)
        raise
    intent = parse_media_intent(reply)
    if intent is None:
        if '"action"' in reply:
            return MediaResult(message=_TRUNC_MSG)
        return MediaResult(message="這個我看不出要做什麼處理。可以說「去背」「轉成 pdf」「縮到 1080 寬」或「改成 300dpi」。")

    src_ext = _ext_of(filename)
    stem = _stem_of(filename)
    action = intent["action"]
    try:
        if action == "remove_bg":
            out = image_tool.remove_background(file_bytes)
            return MediaResult(file=out, filename=f"{stem}-nobg.png",
                               note="去背完成（透明 PNG，以檔案傳回保留透明）。")

        if action == "resize":
            kw = {k: intent[k] for k in ("width", "height", "longest", "percent", "dpi")
                  if intent.get(k) is not None}
            if not kw:
                return MediaResult(message="要調整尺寸或解析度，請告訴我目標（例：縮到 1080 寬、或 300dpi）。")
            out = image_tool.resize_image(file_bytes, src_ext or "png", **kw)
            return MediaResult(file=out, filename=f"{stem}-resized.{src_ext or 'png'}",
                               note="已調整尺寸／解析度。")

        if action == "convert":
            to = (intent.get("to") or "").lstrip(".").lower()
            if not to:
                return MediaResult(message="要轉成什麼格式？例如 pdf、png、jpg。")
            to_out = "jpg" if to in ("jpg", "jpeg") else to
            src_is_image = src_ext in _IMAGE_EXTS
            # 圖片 → 圖片或 PDF：走 sips
            if src_is_image and to in _IMAGE_TARGETS:
                out = image_tool.convert_image(file_bytes, src_ext, to)
                return MediaResult(file=out, filename=f"{stem}.{to_out}",
                                   note=f"已轉成 {to_out.upper()}。")
            # 文件 ↔ 文件/PDF：走 LibreOffice
            if (src_ext in _DOC_EXTS) and (to in _DOC_EXTS):
                try:
                    out = doc_tool.convert_document(file_bytes, src_ext, to)
                except doc_tool.SofficeMissing:
                    return MediaResult(message="文件轉檔需要 LibreOffice。請到控制台「動作工具」按「安裝 LibreOffice」，或自行 brew install --cask libreoffice（圖片功能不受影響）。")
                return MediaResult(file=out, filename=f"{stem}.{to_out}",
                                   note=f"已轉成 {to_out.upper()}。")
            return MediaResult(message=f"這個轉換做不到（{src_ext or '未知'} → {to}）。圖片可轉 png/jpg/tiff/gif/pdf；文件可在 docx/xlsx/pptx/pdf 之間轉。")
    except Exception as e:
        return MediaResult(message=f"處理失敗：{e}")

    return MediaResult(message="沒有可執行的動作。")


def remember_media(file_bytes: bytes, filename: str) -> None:
    """記住 owner 剛傳的圖/檔，供之後純文字跟進指令（如「去背」）套用。"""
    _last_media["bytes"] = file_bytes
    _last_media["filename"] = filename or "file.bin"


def has_remembered_media() -> bool:
    return bool(_last_media.get("bytes"))


def looks_like_media_request(text: str) -> bool:
    """純文字是否像對「上一張圖」下的媒體指令（去背/轉檔/調尺寸）。"""
    t = (text or "").lower()
    return any(h.lower() in t for h in _MEDIA_HINTS)


def handle_media_followup(text: str, now) -> MediaResult:
    """純文字跟進：把指令套用到記住的上一張圖/檔。"""
    if not has_remembered_media():
        return MediaResult(message="我手邊沒有圖片可以處理。請先用「檔案」傳一張圖給我，再說要做什麼（去背／轉檔／調尺寸）🙏")
    return handle_media(text, _last_media["bytes"], _last_media["filename"], now)


_WD = ["一", "二", "三", "四", "五", "六", "日"]


def build_system(now, calendars=None, accounts=None, calendar_on=True, email_on=False, last_list_n=0) -> str:
    today = now.strftime("%Y-%m-%d")
    blocks = []
    if calendar_on:
        cal_line = ("\n  新增時：使用者有明確指定日曆才把名字放進 calendar 欄；"
                    "沒指定就省略 calendar 欄，不要自己編日曆名（例如不要填 default）。")
        if calendars:
            cal_line += "\n  可用日曆：" + "、".join(calendars) + "（指定時請用清單裡的名字）。"
        blocks.append(
            '行事曆：\n'
            '- 新增：{"action":"create","title":"..","start":"YYYY-MM-DDTHH:MM","end":"YYYY-MM-DDTHH:MM","notes":"","calendar":"..","all_day":false}\n'
            '- 查詢：{"action":"list","start":"YYYY-MM-DDT00:00","end":"YYYY-MM-DDT00:00"}\n'
            '- 修改：{"action":"update","match":{"title":"..","date":"YYYY-MM-DD"},"changes":{"start":"..","end":"..","title":".."}}\n'
            '- 刪除：{"action":"delete","match":{"title":"..","date":"YYYY-MM-DD"}}\n'
            '  整天/跨日的事（出差、放假、旅行，或給的是日期範圍如 7/15-7/16、沒有具體時間）→ all_day:true，'
            'start/end 用日期 YYYY-MM-DD（跨日的 end 設成最後一天）；有講具體時間才用 THH:MM。' + cal_line)
    if email_on:
        acc_line = ""
        if accounts:
            acc_line = "\n  可用寄件帳號：" + "、".join(accounts) + "。使用者若指定帳號就放進 account 欄。"
        blocks.append(
            '收發信：\n'
            '- 寄信：{"action":"send_email","to":"a@b.com","subject":"..","body":"..","account":".."}\n'
            '- 列信：{"action":"list_email","scope":"unread","n":10}\n'
            '- 讀信：{"action":"read_email","ref":2,"summarize":false}（剛列出的第幾封）或 {"action":"read_email","match":{"from":"..","subject":".."},"summarize":false}\n'
            '- 刪信：{"action":"delete_email","ref":2}（指涉剛列出的第幾封）或 {"action":"delete_email","match":{"from":"..","subject":".."}}' + acc_line)
    body = "\n".join(blocks)
    body_date = "寄信內文提到日期時，寫成實際日期（例：6/13（週六）），別只寫「禮拜六」。" if email_on else ""
    hint = ""
    if email_on and last_list_n:
        hint = (f"\n注意：使用者剛列出 {last_list_n} 封信（編號 1–{last_list_n}）。"
                f"他說「第幾封」「把N…刪除」「讀第N封」時，多半指這些信，請用 read_email／delete_email 的 ref。")
    return f'''你是個人助理。今天是 {today}（週{_WD[now.weekday()]}）。
**只有當使用者『明確要你動手』操作以下項目時**（查／排／改／刪某筆行程、或收發信），才**只輸出一個 JSON 物件**、不要多餘文字：
{body}
時間用 24 小時制、當地時間；相對日期（明天 / 週四 / 下午三點）依今天換算。{body_date}{hint}
**判斷要保守**：單純陳述、計畫、心情、抱怨、聊到某件事（例如「原本今天要去練背」「最近好忙」「昨天去看電影」）都**不是操作需求** → 正常用繁體中文回答、**絕不要輸出 JSON**。拿不準就當作不是操作。'''


# ── 確認狀態機（pending 存記憶體，單實例一格） ──────────────────
from datetime import datetime, timedelta

_pending = {}
_calendars_cache = []
_mail_accts_cache = []
_last_list = []          # 上次 list_email 的結果，供「刪第 N 封」對應
_last_media = {}         # owner 上次傳的圖/檔（bytes+檔名），供純文字跟進指令套用
_AFFIRM = {"yes", "y", "ok", "好", "對", "確認", "可以", "嗯"}


def reset():
    _pending.clear()
    _calendars_cache.clear()
    _mail_accts_cache.clear()
    _last_list.clear()
    _last_media.clear()


def _writable_calendars():
    if not _calendars_cache:
        try:
            _calendars_cache.extend(cal.list_calendars())
        except Exception:
            pass
    return _calendars_cache


def warm_calendars():
    """開機預熱：把可寫日曆清單抓進 process 快取（off 熱路徑；逾時也不影響開機）。"""
    try:
        _writable_calendars()
    except Exception:
        pass


def _mail_accounts():
    if not _mail_accts_cache:
        try:
            _mail_accts_cache.extend(mail.list_accounts())
        except Exception:
            pass
    return _mail_accts_cache


def _fmt_dt(iso: str) -> str:
    return iso.replace("T", " ")                 # 2026-06-15 15:00


def _md(dstr: str) -> str:
    d = datetime.fromisoformat(dstr)
    return f"{d.month}/{d.day}"


def _wd(dstr: str) -> str:
    return _WD[datetime.fromisoformat(dstr).weekday()]


def _fmt_when(intent) -> str:
    s, e = intent["start"], intent["end"]
    if intent.get("all_day"):
        sd, ed = s[:10], e[:10]
        if sd == ed:
            return f"{_md(sd)}（{_wd(sd)}）整天"
        return f"{_md(sd)}（{_wd(sd)}）–{_md(ed)}（{_wd(ed)}）整天"
    if s[:10] == e[:10]:
        return f"{_fmt_dt(s)}–{e[-5:]}"
    return f"{_fmt_dt(s)} – {_fmt_dt(e)}"


def _fmt_events(evs: list) -> str:
    if not evs:
        return "這段期間沒有行程。"
    return "\n".join(f"{i+1}. {e['title']}（{_fmt_dt(e['start'])}–{e['end'][-5:]}）"
                     for i, e in enumerate(evs))


def _day_window(date_str: str):
    """'YYYY-MM-DD' → (當日 00:00, 隔日 00:00) 給 list 查詢窗。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    nxt = d + timedelta(days=1)
    return d.strftime("%Y-%m-%dT00:00"), nxt.strftime("%Y-%m-%dT00:00")


_is_quota_error = llm.is_quota_error      # 共用 llm 的單一判定
_QUOTA_MSG = llm.QUOTA_MSG
_TRUNC_MSG = "⚠️ 模型回應不完整（多半是額度將滿或暫時異常），動作沒執行。請稍後再試，或切換模型。"


def handle(text: str, now, calendar_on=True, email_on=False):
    """回字串＝agent 處理了；回 None＝非動作，交回 bot 走一般 compose_reply。
    calendar_on/email_on 由 bot 傳入；prompt 只放啟用工具，dispatch 只處理啟用工具。"""
    t = (text or "").strip()
    if "p" in _pending:
        return _advance(t, now)
    cals = _writable_calendars() if calendar_on else []
    accts = _mail_accounts() if email_on else []
    try:
        reply = llm.generate(model=config.MODEL_GENERAL,
                             system=build_system(now, cals, accts, calendar_on, email_on, len(_last_list)),
                             messages=[{"role": "user", "content": text}], max_output_tokens=1024)
    except Exception as e:
        if _is_quota_error(e):
            return _QUOTA_MSG                     # 明確告知額度用完，不誤導成「資料不足」
        _log.warning("意圖分類失敗（%s）→ 當非動作交回一般回覆", type(e).__name__)
        return None                              # 模型/連線錯誤 → 當非動作，交回 bot 走一般回覆（別誤報成 Mail/行事曆）
    intent = parse_intent(reply)
    if intent is None:
        if '"action"' in reply:                  # 模型想動作但 JSON 壞了/截斷 → 不要落到 abstain
            return _TRUNC_MSG
        return None                              # 真非動作 → 交回 bot（含 RAG）
    if not IS_MACOS:
        return _NOT_MACOS_MSG                     # 偵測到動作但非 macOS → 不碰 osascript
    is_email = intent["action"] in _EMAIL_ACTIONS
    if is_email and not email_on:
        return None                              # 未啟用該工具 → 不誤動作，交回 bot
    if (not is_email) and not calendar_on:
        return None
    return _begin(intent)


def _fmt_inbox(msgs: list) -> str:
    if not msgs:
        return "沒有符合的信件。"
    return "\n".join(f"{i+1}. {m['from']}｜{m['subject']}" for i, m in enumerate(msgs))


def _begin(intent):
    action = intent["action"]
    if action == "list_email":
        msgs = mail.list_inbox(intent.get("scope", "unread"), intent.get("n", 10))
        _last_list.clear()
        _last_list.extend(msgs)
        return _fmt_inbox(msgs)
    if action == "send_email":
        return _begin_send(intent)
    if action == "read_email":
        return _begin_read(intent)
    if action == "delete_email":
        return _begin_delete(intent)
    if action == "list":
        return _fmt_events(cal.list_events(intent["start"], intent["end"]))
    if action == "create":
        return _begin_create(intent)
    return _begin_modify(intent)


def _begin_create(intent):
    writable = _writable_calendars()
    req = (intent.get("calendar") or "").strip()
    if req and writable and req.lower() not in [w.lower() for w in writable]:
        req = ""                                       # 清單在、名字不在清單 → 不採信（擋幻覺如 default）
    cal_name = req or config.CALENDAR_NAME
    if cal_name:
        return _confirm_create(intent, cal_name)
    if len(writable) > 1:
        _pending["p"] = {"kind": "pick_calendar", "intent": intent, "cals": writable}
        listing = "\n".join(f"{i+1}. {c}" for i, c in enumerate(writable))
        return f"要加到哪一本日曆？（回編號）\n{listing}"
    if len(writable) == 1:
        return _confirm_create(intent, writable[0])
    return _confirm_create_default(intent)             # writable 空、又沒指定 → 誠實降級


def _confirm_create_default(intent):
    _pending["p"] = {"kind": "confirm", "action": "create", "intent": intent, "calendar": ""}
    return ("（暫時讀不到你的日曆清單，先放到系統預設日曆；之後可在日曆 App 拖到別本）\n"
            f"要我新增「{intent['title']}」 {_fmt_when(intent)} 嗎？（回 yes 確認）")


def _confirm_create(intent, cal_name):
    _pending["p"] = {"kind": "confirm", "action": "create", "intent": intent, "calendar": cal_name}
    where = f"到【{cal_name}】" if cal_name else ""
    return (f"要我新增「{intent['title']}」{where} "
            f"{_fmt_when(intent)} 嗎？（回 yes 確認）")


def _advance_pick_calendar(t):
    pend = _pending["p"]
    if not t.isdigit() or not (1 <= int(t) <= len(pend["cals"])):
        _pending.clear()
        return "已取消。"
    return _confirm_create(pend["intent"], pend["cals"][int(t) - 1])


def _begin_send(intent):
    acct = intent.get("account") or config.MAIL_ACCOUNT
    if acct:
        return _confirm_send(intent, acct)
    accounts = _mail_accounts()
    if len(accounts) <= 1:
        return _confirm_send(intent, accounts[0] if accounts else "")
    _pending["p"] = {"kind": "pick_account", "intent": intent, "accounts": accounts}
    listing = "\n".join(f"{i+1}. {a}" for i, a in enumerate(accounts))
    return f"要用哪個帳號寄？（回編號）\n{listing}"


def _confirm_send(intent, account):
    _pending["p"] = {"kind": "confirm", "action": "send_email", "intent": intent, "account": account}
    frm = f"（從 {account}）" if account else ""
    return (f"要寄這封嗎？{frm}（回 yes 確認）\n"
            f"收件人：{intent.get('to', '')}\n主旨：{intent.get('subject', '')}\n"
            f"———\n{intent.get('body', '')}")


def _advance_pick_account(t):
    pend = _pending["p"]
    if not t.isdigit() or not (1 <= int(t) <= len(pend["accounts"])):
        _pending.clear()
        return "已取消。"
    return _confirm_send(pend["intent"], pend["accounts"][int(t) - 1])


def _begin_read(intent):
    summarize = bool(intent.get("summarize"))
    ref = intent.get("ref")
    if ref is not None:
        msg, err = _ref_msg(ref)
        return err if err else _do_read(msg["id"], summarize)
    match = intent.get("match", {})
    fr = (match.get("from") or "").lower()
    su = (match.get("subject") or "").lower()
    cands = [m for m in mail.list_inbox("recent", 30)
             if fr in m["from"].lower() and su in m["subject"].lower()]
    if not cands:
        return "找不到符合的信件。"
    if len(cands) == 1:
        return _do_read(cands[0]["id"], summarize)
    _pending["p"] = {"kind": "select_email", "cands": cands, "summarize": summarize, "op": "read"}
    listing = "\n".join(f"{i+1}. {c['from']}｜{c['subject']}" for i, c in enumerate(cands))
    return f"找到多封，要讀哪一封？（回編號）\n{listing}"


def _ref_msg(ref):
    """把「第幾封」對應到 _last_list；回 (msg, None) 或 (None, 錯誤訊息)。"""
    if not _last_list:
        return None, "請先列信，再說第幾封。"
    try:
        idx = int(ref)
    except (TypeError, ValueError):
        return None, "請先列信，再說第幾封。"
    if not (1 <= idx <= len(_last_list)):
        return None, f"清單裡沒有第 {ref} 封。"
    return _last_list[idx - 1], None


def _begin_delete(intent):
    ref = intent.get("ref")
    if ref is not None:
        msg, err = _ref_msg(ref)
        return err if err else _confirm_delete(msg)
    match = intent.get("match", {})
    fr = (match.get("from") or "").lower()
    su = (match.get("subject") or "").lower()
    cands = [m for m in mail.list_inbox("recent", mail.MAX_SCAN)
             if fr in m["from"].lower() and su in m["subject"].lower()]
    if not cands:
        return "找不到符合的信件。"
    if len(cands) == 1:
        return _confirm_delete(cands[0])
    _pending["p"] = {"kind": "select_email", "cands": cands, "op": "delete"}
    listing = "\n".join(f"{i+1}. {c['from']}｜{c['subject']}" for i, c in enumerate(cands))
    return f"找到多封，要刪哪一封？（回編號）\n{listing}"


def _confirm_delete(msg):
    _pending["p"] = {"kind": "confirm", "action": "delete_email", "msg": msg}
    return f"要刪除「{msg['from']}｜{msg['subject']}」嗎？（回 yes，會移到垃圾桶、可復原）"


def _do_read(msg_id, summarize):
    m = mail.read_message(msg_id)
    if summarize:
        s = llm.generate(model=config.MODEL_GENERAL, system="用繁體中文 2-3 句摘要這封信。",
                         messages=[{"role": "user", "content": m["body"]}], max_output_tokens=300)
        return f"【{m['subject']}】來自 {m['from']}\n摘要：{s}"
    return f"【{m['subject']}】來自 {m['from']}\n{m['body'][:1500]}"


def _advance_select_email(t):
    pend = _pending["p"]
    if not t.isdigit() or not (1 <= int(t) <= len(pend["cands"])):
        _pending.clear()
        return "已取消。"
    msg = pend["cands"][int(t) - 1]
    if pend.get("op") == "delete":
        return _confirm_delete(msg)              # 覆寫 pending 為 confirm
    _pending.clear()
    return _do_read(msg["id"], pend.get("summarize"))


def _begin_modify(intent):
    action = intent["action"]
    match = intent.get("match", {})
    title_q = (match.get("title") or "").lower()
    date = match.get("date")
    if not date:
        return "請告訴我是哪一天的行程？"
    s, e = _day_window(date)
    cands = [ev for ev in cal.list_events(s, e) if title_q in ev["title"].lower()]
    if not cands:
        return "找不到符合的行程。"
    if len(cands) == 1:
        return _to_confirm(action, cands[0], intent.get("changes"))
    _pending["p"] = {"kind": "select", "action": action,
                     "cands": cands, "changes": intent.get("changes")}
    listing = "\n".join(f"{i+1}. {c['title']}（{_fmt_dt(c['start'])}）" for i, c in enumerate(cands))
    verb = "刪除" if action == "delete" else "修改"
    return f"找到多筆，要{verb}哪一個？（回編號）\n{listing}"


def _to_confirm(action, ev, changes):
    _pending["p"] = {"kind": "confirm", "action": action, "ev": ev, "changes": changes}
    if action == "delete":
        return f"要刪除「{ev['title']}」{_fmt_dt(ev['start'])} 嗎？（回 yes 確認）"
    return f"要把「{ev['title']}」改成 {_fmt_dt(changes.get('start', ev['start']))} 嗎？（回 yes 確認）"


_CANCEL = {"取消", "不要", "不用", "不用了", "算了", "no", "不寄", "不寄了", "cancel"}


def _advance(t, now):
    pend = _pending["p"]
    if pend["kind"] == "select":
        return _advance_select(t)
    if pend["kind"] == "pick_calendar":
        return _advance_pick_calendar(t)
    if pend["kind"] == "pick_account":
        return _advance_pick_account(t)
    if pend["kind"] == "select_email":
        return _advance_select_email(t)
    # confirm
    if t.lower() in _AFFIRM:
        _pending.clear()
        return _execute(pend)
    if t.strip().lower() in _CANCEL:            # 明確取消詞才取消
        _pending.clear()
        return "已取消。"
    action = pend.get("action")                 # 其餘非-yes → 重新解讀，絕不靜默取消
    if action == "send_email":
        return _refine_send(pend, t, now)
    if action == "create":
        return _refine_create(pend, t, now)
    if action in ("update", "delete"):
        return _refine_modify(pend, t, now)
    _pending.clear()
    return "已取消。"


def _refine_send(pend, instruction, now):
    i = pend["intent"]
    today = now.strftime("%Y-%m-%d")
    sys = (f"今天是 {today}（週{_WD[now.weekday()]}）。以下是一封 email 草稿，使用者要你修改。"
           '只輸出修改後的 JSON：{"to":"..","subject":"..","body":".."}，不要多餘文字。'
           "內文若有相對日期（禮拜六/明天）請換算成實際日期（例：6/13（週六））。")
    user = (f"草稿：\n收件人：{i.get('to', '')}\n主旨：{i.get('subject', '')}\n內文：{i.get('body', '')}\n\n"
            f"修改要求：{instruction}")
    rev = _extract_json(llm.generate(model=config.MODEL_GENERAL, system=sys,
                                     messages=[{"role": "user", "content": user}], max_output_tokens=800))
    if not isinstance(rev, dict) or not rev.get("body"):
        return "我沒抓到要怎麼改，請再說一次（或回 yes 寄出 / 取消）。"   # 保留原草稿
    new_intent = dict(i)
    for k in ("to", "subject", "body"):
        if rev.get(k):
            new_intent[k] = rev[k]
    return _confirm_send(new_intent, pend.get("account", ""))   # 重新預覽（覆寫 pending）


def _refine_create(pend, instruction, now):
    i = pend["intent"]
    today = now.strftime("%Y-%m-%d")
    sys = (f"今天是 {today}（週{_WD[now.weekday()]}）。以下是一個行事曆事件草稿，使用者要你修改。"
           '只輸出修改後的 JSON：{"title":"..","start":"..","end":"..","all_day":true/false}，不要多餘文字。'
           "日期範圍或整天的事用 all_day:true、start/end 用 YYYY-MM-DD；有具體時間才用 YYYY-MM-DDTHH:MM。")
    cur = (f"草稿：標題「{i.get('title', '')}」，"
           f"{'整天 ' if i.get('all_day') else ''}{i.get('start', '')}–{i.get('end', '')}\n\n修改要求：{instruction}")
    rev = _extract_json(llm.generate(model=config.MODEL_GENERAL, system=sys,
                                     messages=[{"role": "user", "content": cur}], max_output_tokens=400))
    if not isinstance(rev, dict) or not rev.get("start"):
        return "我沒抓到要怎麼改，請再說一次（或回 yes 確認 / 取消）。"   # 保留 pending
    new_intent = dict(i)
    for k in ("title", "start", "end", "all_day"):
        if k in rev:
            new_intent[k] = rev[k]
    return _confirm_create(new_intent, pend.get("calendar", ""))


def _refine_modify(pend, instruction, now):
    action, ev = pend["action"], pend["ev"]
    today = now.strftime("%Y-%m-%d")
    verb = "刪除" if action == "delete" else "修改"
    sys = (f"今天是 {today}（週{_WD[now.weekday()]}）。使用者正在{verb}一個行事曆事件，"
           f"目前鎖定：「{ev['title']}」{_fmt_dt(ev['start'])}。他要更正/補充。\n"
           f'只輸出一個 JSON：{{"action":"{action}","match":{{"title":"..","date":"YYYY-MM-DD"}},'
           '"changes":{"start":"..","end":"..","title":".."}}，delete 不需 changes。不要多餘文字。')
    new_intent = _extract_json(llm.generate(model=config.MODEL_GENERAL, system=sys,
                                            messages=[{"role": "user", "content": instruction}], max_output_tokens=400))
    if not isinstance(new_intent, dict) or new_intent.get("action") not in ("update", "delete"):
        return "我沒抓到要怎麼改，請再說一次（或回 yes 確認 / 取消）。"   # 保留 pending
    return _begin_modify(new_intent)


def _advance_select(t):
    pend = _pending["p"]
    if not t.isdigit() or not (1 <= int(t) <= len(pend["cands"])):
        _pending.clear()
        return "已取消。"
    ev = pend["cands"][int(t) - 1]
    return _to_confirm(pend["action"], ev, pend["changes"])


def _execute(pend):
    result = _execute_impl(pend)
    try:
        memory.append(config.OWNER_CHAT_ID, "action", result, alias=config.OWNER_NAME)
    except Exception:
        pass        # 記憶失敗不可影響動作本身
    return result


def _execute_impl(pend):
    a = pend["action"]
    if a == "send_email":
        i = pend["intent"]
        mail.send_mail(i.get("to", ""), i.get("subject", ""), i.get("body", ""), pend.get("account", ""))
        return f"已寄出給 {i.get('to', '')}。"
    if a == "delete_email":
        m = pend["msg"]
        mail.delete_message(m["id"])
        return f"已刪除「{m['subject']}」（在垃圾桶可復原）。"
    if a == "create":
        i = pend["intent"]
        cal.create_event(i["title"], i["start"], i["end"], i.get("notes", ""),
                         calendar=pend.get("calendar", ""), all_day=bool(i.get("all_day")))
        where = f"到【{pend['calendar']}】" if pend.get("calendar") else ""
        return f"已新增「{i['title']}」{where} {_fmt_when(i)}。"
    ev = pend["ev"]
    if a == "delete":
        cal.delete_event(ev["uid"])
        return f"已刪除「{ev['title']}」。"
    cal.update_event(ev["uid"], pend["changes"] or {})
    return f"已更新「{ev['title']}」。"
