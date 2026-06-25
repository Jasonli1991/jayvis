import asyncio
import logging
import re
import sys
import time
from io import BytesIO
from pathlib import Path

try:
    import fcntl              # Unix（macOS/Linux）：單一實例用 flock 檔案鎖
except ImportError:
    fcntl = None              # Windows 無 fcntl，改綁 localhost 埠當互斥鎖（見 acquire_single_instance_lock）

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TimedOut

from datetime import datetime

import agent
import analysis
import config
import cooldown
import group_memory
import guard
import inbox_capture
import llm
import leave_digest
import browse_agent
import image_gen
import browse_tool
import browse_allowlist
import code_delegate
import memory
import persona
from assistant import compose_reply
from panel import env_io

logging.basicConfig(level=logging.INFO, format="%(asctime)s｜%(levelname)s:%(name)s:%(message)s",
                    datefmt="%m-%d %H:%M:%S")     # 每行帶時間，即時 Log 看得到何時發生
# 第三方 INFO 噪音：httpx 每次 long-poll 都印一行（且 URL 內含 bot token！）、
# telegram.ext 的 Application started/stopping/stop() complete 生命週期、apscheduler 排程、
# google-genai 每次呼叫印「AFC is enabled…」（我們沒用 function calling、純噪音）。
# 壓到 WARNING：保留真正的警告/錯誤，砍掉每次重啟的洗版與 token 落地 bot.log。
_QUIET_LOGGERS = ("httpx", "httpcore", "telegram", "apscheduler",
                  "google_genai", "google.genai", "google")
for _n in _QUIET_LOGGERS:
    logging.getLogger(_n).setLevel(logging.WARNING)
_log = logging.getLogger("jayvis")

# 單一實例鎖：保證同一時間只有一個 bot 在對 Telegram 輪詢。
# 根因——面板的 start() 只靠單一 .bot.pid 判定，無 OS 鎖、Flask 多執行緒下無互斥，
# 競態時會 spawn 兩隻 bot.py，兩隻都 long-poll 同一 token → telegram.error.Conflict 無限噴。
# 在 bot 自己這層上鎖最可靠：任何多餘實例一啟動就拿不到鎖、立即結束，從源頭杜絕 Conflict。
# Unix（macOS/Linux）用 flock 檔案鎖；Windows（無 fcntl）改綁 localhost 固定埠當互斥鎖——兩者皆隨程序結束自動釋放。
_LOCK_FILE = Path(__file__).resolve().parent / ".bot.lock"
_LOCK_PORT = 47923   # Windows 用：綁這個 127.0.0.1 埠當單一實例鎖（綁不到＝已有實例）
_lock_fp = None      # 持有到程序結束以維持鎖（Unix 為檔案物件、Windows 為 socket）；務必保留參考勿讓 GC 收掉


def acquire_single_instance_lock(lock_path=None):
    """取得單一實例鎖。回 (True, holder)＝成功（呼叫端須保留 holder 直到程序結束）；
    回 (False, None)＝已有實例持鎖（呼叫端應立即結束，避免 getUpdates Conflict）。
    holder 隨程序結束自動釋放，不會像 .bot.pid 留下髒狀態（殺不掉的孤兒）。"""
    if fcntl is not None:                                   # macOS/Linux：flock 檔案鎖（行為與原本完全一致）
        fp = open(lock_path or _LOCK_FILE, "w")
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            fp.close()
            return False, None
        return True, fp
    import socket                                           # Windows：綁 127.0.0.1 固定埠，綁不到代表已有實例
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
    except OSError:
        s.close()
        return False, None
    return True, s

_pending_browse = {}                  # owner_id -> {"pending": dict, "ts": float}
_BROWSE_PENDING_TTL_S = 300           # 確認請求過期時間（秒）

_browse_session = {}                  # owner_id -> last_activity_ts（瀏覽模式中）
_BROWSE_SESSION_TTL_S = 600           # 閒置逾 10 分鐘自動離開瀏覽模式
_BROWSE_STOP_WORDS = ("結束瀏覽", "停止瀏覽", "離開瀏覽", "結束瀏覽模式", "退出瀏覽")

_pending_allow = {}                   # owner_id -> {"domain","task","url"}：被擋網域待 owner 同意加白名單

_BROWSE_HINT = ("瀏覽", "網站", "網頁", "打開網", "查網", "逛", "後台", "截圖", "首頁")

# 裸網域偵測（如 ka2ka.com、admin.example.com.tw）；不用 \b 因中文字旁不形成詞界。
_DOMAIN_RE = re.compile(
    r'(?:https?://)?(?:[a-z0-9-]+\.)+'
    r'(?:com|net|org|io|ai|app|dev|co|me|tw|cc|xyz|info|gov|edu)(?:/\S*)?', re.I)


def _extract_browse_url(text: str):
    """從訊息抓出第一個網址/裸網域，正規化成完整 URL；沒有則 None。"""
    m = _DOMAIN_RE.search(text or "")
    if not m:
        return None
    u = m.group(0)
    return u if u.lower().startswith(("http://", "https://")) else "https://" + u


def _looks_like_browse(text: str) -> bool:
    t = text or ""
    if _extract_browse_url(t):                 # 出現網址/裸網域 → 視為瀏覽意圖
        return True
    return any(h in t for h in _BROWSE_HINT)


# 明確要圖的關鍵字（精準到詞，避免「計畫」「畫面」誤觸發）
_IMG_REQ_HINT = ("畫一", "畫個", "畫張", "畫幅", "畫出", "幫我畫", "幫忙畫", "繪製",
                 "梗圖", "插圖", "海報", "貼圖", "logo")
# 「動詞 + （中間幾個字）+ 圖」彈性比對：抓「做一張三大天王的圖」「幫我生一張…的圖片」等自然講法
_IMG_REQ_RE = re.compile(r"(畫|做|生成|產生|弄|設計|給我|來|幫我做|幫我畫|幫我生).{0,12}?(圖|圖片|圖像|插畫)")


def _looks_like_image_request(text: str) -> bool:
    t = (text or "").lower()
    if any(h in t for h in _IMG_REQ_HINT):
        return True
    return bool(_IMG_REQ_RE.search(t))


def _recent_context(uid: int, n: int = 4) -> str:
    """最近 n 輪對話的精簡文字，供生圖解析『三大天王』之類的指涉。"""
    try:
        turns = memory.recent(uid)[-n * 2:]
        return "\n".join(f"{'我' if t.get('role') == 'user' else '搭檔'}："
                         f"{(t.get('content') or '')[:120]}" for t in turns)
    except Exception:
        return ""


def _is_confirm_reply(text: str) -> bool:
    return (text or "").strip() in ("確認", "好", "可以", "yes", "y", "取消", "不要", "no", "n")


def _is_yes(text: str) -> bool:
    return (text or "").strip() in ("確認", "好", "可以", "yes", "y")


async def _deliver_browse(msg, context, res, uid) -> None:
    from io import BytesIO
    if res.status == "pending":
        _pending_browse[uid] = {"pending": res.pending, "ts": time.time()}
        await msg.reply_text(f"⚠️ 這個動作會改東西：{res.summary}\n要我執行嗎？回「確認」或「取消」。")
    else:
        await _send_long(msg, res.summary or "（沒有內容）")
    if res.screenshot:
        await context.bot.send_photo(chat_id=msg.chat_id, photo=BytesIO(res.screenshot))


async def _run_browse(msg, context, user, task, start_url) -> None:
    """跑一次瀏覽任務並把結果送出；統一處理沒就緒／非白名單／其他例外。"""
    _log.info("🌐 瀏覽 %s：%s%s", _who(user), _preview(task),
              f"（→{start_url}）" if start_url else "")
    try:
        t0 = time.time()
        res = await asyncio.to_thread(browse_agent.run, task, start_url)
        _log.info("🌐 瀏覽結果 status=%s（%.1fs，%s）", res.status, time.time() - t0,
                  "有截圖" if getattr(res, "screenshot", None) else "無圖")
        await _deliver_browse(msg, context, res, user.id)
    except browse_tool.BrowseUnavailable:
        _log.warning("🌐 瀏覽器未就緒")
        _browse_session.pop(user.id, None)           # 沒就緒就別把人困在瀏覽模式
        await msg.reply_text(
            "瀏覽器還沒就緒。請到控制台面板把「啟用網站瀏覽」打開"
            "（會自動開啟專用瀏覽器），第一次記得在那個視窗登入要用的網站，再回我一次 🙏")
    except browse_tool.NotAllowed as e:
        from urllib.parse import urlparse
        dom = urlparse(str(e)).hostname or str(e)
        _pending_allow[user.id] = {"domain": dom, "task": task, "url": str(e)}
        await msg.reply_text(f"「{dom}」不在我的瀏覽白名單，要我加進去嗎？回「好」即可。")
    except Exception as e:
        browse_tool.reset()
        await msg.reply_text("瀏覽出了點狀況，我先停手 🙏")
        await notify_owner_error(context.bot, e, where="瀏覽網頁")


def is_owner(user_id: int) -> bool:
    return config.OWNER_CHAT_ID != 0 and user_id == config.OWNER_CHAT_ID


def is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWLIST_USER_IDS or is_owner(user_id)   # owner 免加白名單


def non_allowlist_reply(chat_type: str):
    """非白名單發話者：群組裡（已 @ bot）回一句婉拒；私訊陌生人則不回（None）。"""
    if chat_type in ("group", "supergroup"):
        return "我無法接受您的指令喔🥹"
    return None


def _preview(text: str, n: int = 30) -> str:
    """活動 log 用的短預覽：收斂換行/多空白，超過 n 字截斷。完整內容看記憶時間軸。"""
    t = " ".join((text or "").split())
    return (t[:n] + "…") if len(t) > n else t


def _who(user) -> str:
    """訊息對象的顯示名：白名單別名 → owner 名 → TG 顯示名 → id。"""
    return (config.ALLOWLIST_ALIASES.get(user.id)
            or (config.OWNER_NAME if is_owner(user.id) else None)
            or user.full_name or str(user.id))


def _format_apply_report(proj, q, res):
    """把 code_delegate.apply() 回傳的 dict 轉成給 owner 的回報文字（Phase C1）。"""
    if not res.get("ok"):
        base = f"⚠️ {proj} 自動修復沒完成：{res.get('error') or '未知錯誤'}\n問題：{q}"
        if res.get("alarm"):
            base += f"\n\n{res['alarm']}"
        if res.get("pr_url"):
            base += f"\n（仍有 PR：{res['pr_url']}）"
        if res.get("summary"):
            base += f"\n\n📄 Agent 末段：\n{res['summary']}"
        return base
    lines = [f"✅ {proj} 已開 PR — 由「{q}」觸發", "", f"🔗 {res['pr_url']}"]
    tmap = {"pass": "✅ 測試全過", "fail": "⚠️ 測試有失敗（PR 內有列）",
            "none": "❔ 此專案沒有測試，改動未經自動驗證，請務必人工 review"}
    lines.append(tmap.get(res.get("tests"),
                          "⚠️ 測試狀態不明（Agent 未回報，可能逾時或超預算中斷，請人工確認）"))
    if res.get("warn"):
        lines += ["", f"⚠️ {res['warn']}"]
    if res.get("alarm"):
        lines += ["", res["alarm"]]
    if res.get("summary"):
        lines += ["", res["summary"]]
    return "\n".join(lines)


def _cooldown_exempt(user) -> bool:
    """owner 一律豁免；同事若白名單別名對得上身份設定的老闆名字也豁免（寬鬆比對）。"""
    if is_owner(user.id):
        return True
    alias = (config.ALLOWLIST_ALIASES.get(user.id)
             or getattr(user, "full_name", "") or "").strip().lower()
    if not alias:
        return False
    try:
        bosses = [b.get("name", "").strip().lower()
                  for b in (persona.load_profile().get("bosses") or []) if b.get("name")]
    except Exception:
        bosses = []
    return any(alias == b or alias in b or b in alias for b in bosses)


def _format_analysis(result) -> str:
    ans = result.get("answer") or "（無結果）"
    srcs = result.get("sources") or []
    if srcs:
        ans += "\n\n— 依據：" + "、".join(srcs[:8])
    return ans


async def _send_long(msg, text, limit=3500):
    """超過 Telegram 單則上限（4096）時切段依序送。"""
    text = text or "（無內容）"
    for i in range(0, len(text), limit):
        await msg.reply_text(text[i:i + limit])


async def _send_long_chat(tg_bot, chat_id, text, limit=3500):
    """把長訊息切段送到指定 chat（如 owner 私訊）。"""
    text = text or "（無內容）"
    for i in range(0, len(text), limit):
        await tg_bot.send_message(chat_id=chat_id, text=text[i:i + limit])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if msg is None or user is None or chat is None:
        return

    text = (msg.text or msg.caption or "").strip()

    is_group = chat.type in ("group", "supergroup")
    if is_group:
        # 一律記錄群組對話（含非白名單者）建立完整脈絡。
        # owner 用 OWNER_NAME、同事用別名 → transcript 的發話者與 prompt 裡的身份一致，
        # JAYVIS 回顧群組歷史時才認得出「這是我 owner」（不靠 TG 顯示名碰運氣）。
        speaker = (config.OWNER_NAME if user.id == config.OWNER_CHAT_ID
                   else config.ALLOWLIST_ALIASES.get(user.id)) or user.full_name or str(user.id)
        group_memory.record(chat.id, speaker, text)
        # 只在被 @ 時回應，並剝掉 @mention
        uname = context.bot.username
        if not uname or f"@{uname}" not in text:
            return
        text = text.replace(f"@{uname}", "").strip()

    if not is_allowed(user.id):
        _log.info("🚫 擋下非白名單 %s（%s）", user.id, _preview(text) or "（無文字）")
        reply = non_allowlist_reply(chat.type)
        if reply:
            await msg.reply_text(reply)
        return

    # 同事冷卻閘：非豁免者（同事）高頻且整批低優先 → 鎖 60 分。owner／老闆豁免、常駐。
    if not _cooldown_exempt(user):
        now = time.time()
        pid = str(user.id)
        if cooldown.is_locked(pid, now):
            _log.info("🧊 冷卻中靜默 %s", _who(user))
            return
        cooldown.record(pid, now, text)
        if cooldown.over_rate(pid, now) and cooldown.looks_low_priority(cooldown.recent_texts(pid, now)):
            cooldown.lock(pid, now)
            _log.info("🧊 冷卻 %s（低優先高頻）→ 鎖 60 分", _who(user))
            await msg.reply_text("我先忙一下，大約 60 分鐘後再聊喔 🙏")
            return

    # 活動監控：記下這則被處理的訊息（事件＋對象＋短預覽；完整內容在記憶時間軸）
    _scope = f"群組「{chat.title or chat.id}」" if is_group else "私訊"
    _log.info("📩 %s %s：%s", _scope, _who(user), _preview(text) or "（圖片／檔案）")

    # owner 私訊回「存」：把上一則知識問答寫進 Obsidian Inbox（需有暫存）
    if (not is_group and is_owner(user.id) and inbox_capture.is_save_command(text)
            and inbox_capture.has_pending()):
        cap = inbox_capture.take()
        ok, info = inbox_capture.save_to_inbox(cap["q"], cap["a"], datetime.now())
        _log.info("🗂 Inbox 捕捉 %s：%s", "成功" if ok else "失敗", info)
        await msg.reply_text(f"✅ 已存進 00_Raw/Inbox：{info}" if ok else info)
        return

    # owner 私訊「分析：…」→ 深度分析（廣撈、強模型、長報告）。僅私訊（群組廣撈會外洩）。
    _am = re.match(r"^\s*分析[:：]\s*(.+)", text, re.S) if text else None
    if not is_group and is_owner(user.id) and _am:
        q = _am.group(1).strip()
        _log.info("🔍 分析（TG）：%s", _preview(q))
        try:
            result = await asyncio.to_thread(analysis.analyze, q)
            await _send_long(msg, _format_analysis(result))
        except Exception:
            _log.exception("analysis failed for owner_id=%s", user.id)
            await msg.reply_text("分析時出了點狀況，等一下再試 🙏")
        return

    # owner 純文字媒體跟進：對「上一張傳來的圖」下指令（如剛傳圖、接著只打「去背」）。
    # 放在行事曆/收信前攔截，且需真的有記住的圖才接手，否則照常往下走（不綁架一般聊天）。
    # 群組亦可（owner 本人被 @ 才會到這；同事非 owner 不進）。
    if (config.MEDIA_ENABLED and is_owner(user.id)
            and text and not msg.photo and msg.document is None
            and agent.looks_like_media_request(text) and agent.has_remembered_media(msg.chat_id)):
        result = await asyncio.to_thread(agent.handle_media_followup, text, datetime.now(), msg.chat_id)
        if result.file is not None:
            _log.info("🖼 媒體（跟進上一張圖）→ %s", result.filename)
            await msg.reply_document(document=BytesIO(result.file), filename=result.filename, caption=result.note)
        else:
            await msg.reply_text(result.message)
        if not is_group:                                # 私訊才記進線性脈絡（群組脈絡走 group_memory，不污染私訊記憶）
            _outcome = f"已處理上一張圖 → {result.filename}" if result.file is not None else result.message
            memory.append(user.id, "user", text, alias=config.OWNER_NAME)
            memory.append(user.id, "assistant", _outcome, alias=config.OWNER_NAME)
        return

    # owner-only 動作（行事曆 / 收發信）：私訊 + owner + 任一啟用 + 純文字才走（無附檔）；
    # 非動作回 None → 往下走一般 compose_reply（含 RAG）。同事/群組永不進此分支。
    if (not is_group and (config.ACTIONS_ENABLED or config.EMAIL_ENABLED)
            and is_owner(user.id) and text and not msg.photo and msg.document is None):
        try:
            action_reply = await asyncio.to_thread(
                agent.handle, text, datetime.now(), config.ACTIONS_ENABLED, config.EMAIL_ENABLED)
        except Exception:
            _log.exception("agent.handle failed for owner_id=%s", user.id)
            await msg.reply_text("動作執行時出了點狀況（可能 Mail／行事曆沒回應，或尚未授權控制）。等一下再試 🙏")
            return
        if action_reply is not None:
            _log.info("🛠 動作 %s", _preview(action_reply))
            await msg.reply_text(action_reply)
            # 把動作互動（含唯讀查詢、確認流程）記進對話脈絡，讓 JAYVIS 下一輪記得自己剛做了什麼。
            # 唯讀查詢（如「今天有什麼會議」）不會產生 kind="action" 記錄，故這裡是它唯一的記憶來源。
            memory.append(user.id, "user", text, alias=config.OWNER_NAME)
            memory.append(user.id, "assistant", action_reply, alias=config.OWNER_NAME)
            return

    # owner 媒體工具（去背/轉檔/調尺寸）：owner + 啟用 + 帶檔案才走（私訊或群組被 @）。
    # 文件一律進；照片需有說明（caption），讓無說明的照片仍走一般視覺對話。
    if (config.MEDIA_ENABLED and is_owner(user.id)
            and (msg.document is not None
                 or (msg.photo and text and agent.looks_like_media_request(text)))):
        try:
            if msg.document is not None:
                f = await msg.document.get_file()
                raw = bytes(await f.download_as_bytearray())
                fname = msg.document.file_name or "file.bin"
            else:
                f = await msg.photo[-1].get_file()
                raw = bytes(await f.download_as_bytearray())
                fname = "photo.jpg"
        except Exception:
            _log.exception("media download failed for owner_id=%s", user.id)
            await msg.reply_text("檔案太大或下載失敗（Telegram 機器人下載上限約 20MB）。請傳小一點的檔案 🙏")
            return
        agent.remember_media(raw, fname, msg.chat_id)   # 記住（綁該對話），供之後純文字跟進指令套用
        result = await asyncio.to_thread(agent.handle_media, text, raw, fname, datetime.now())
        if result.file is not None:
            _log.info("🖼 媒體 %s → %s", fname, result.filename)
            cap = result.note
            if not msg.document:   # 來源是被壓過的 photo → 提醒原圖品質
                cap = ((cap + "\n") if cap else "") + "（這是 Telegram 壓過的圖；想要原畫質/去背更乾淨，請用「檔案」方式傳原圖。）"
            await msg.reply_document(document=BytesIO(result.file), filename=result.filename, caption=cap)
        else:
            await msg.reply_text(result.message)
        if not is_group:                                # 私訊才記進線性脈絡（群組不污染私訊記憶）
            _outcome = f"已處理 {fname} → {result.filename}" if result.file is not None else result.message
            memory.append(user.id, "user", text or f"[傳了檔案 {fname}]", alias=config.OWNER_NAME)
            memory.append(user.id, "assistant", _outcome, alias=config.OWNER_NAME)
        return

    image_bytes = None
    if msg.photo:
        f = await msg.photo[-1].get_file()
        ba = await f.download_as_bytearray()
        image_bytes = bytes(ba)
        if config.MEDIA_ENABLED and is_owner(user.id):
            agent.remember_media(image_bytes, "photo.jpg", msg.chat_id)   # 無說明的照片也記住（綁該對話）

    if not text and image_bytes is None:
        if env_io.is_on_leave():
            await msg.reply_text(f"我是 {config.ASSISTANT_NAME}，{config.OWNER_NAME} 請假中；有問題可以直接發訊息給我～")
        else:
            await msg.reply_text(f"我是 {config.OWNER_NAME} 的 AI 搭檔～有什麼需要可以直接問我 😊")
        return

    if text and guard.is_injection(text):
        await msg.reply_text("這我沒辦法喔 😅 有正事我很樂意幫忙")
        return

    # Phase C：核准執行（owner 看完計畫回「執行」）→ Agent 在分支改碼+測試+開 PR
    if (text and not is_group and config.CODE_ROOT and is_owner(user.id)
            and code_delegate.is_apply_command(text) and code_delegate.has_apply(user.id)):
        proj, q, plan, origin_chat = code_delegate.take_apply(user.id)
        _log.info("🚀 核准執行 %s → 專案 %s", _who(user), proj)
        await msg.reply_text(f"好，正在對 {proj} 改碼、跑測試、開 PR，最多約 10 分鐘，完成或逾時我都會回你。")
        res = await asyncio.to_thread(code_delegate.apply, proj, q, plan, datetime.now())
        await _send_long(msg, _format_apply_report(proj, q, res))
        if origin_chat:
            if res.get("ok") and res.get("clean"):
                note = f"你問的 {proj} 問題我已著手處理，{config.OWNER_NAME} 審完會再跟你說 🙏"
            else:
                note = f"你問的 {proj} 問題還在處理中，{config.OWNER_NAME} 會再跟你說 🙏"
            await context.bot.send_message(chat_id=origin_chat, text=note)
        return

    # Phase B：修復計畫觸發（asker 回「修復計畫」且有暫存）→ Agent 擬計畫 → 送 owner 審
    if (text and not is_group and config.CODE_ROOT
            and (is_owner(user.id) or env_io.is_on_leave())
            and code_delegate.is_fix_command(text) and code_delegate.has_fix(user.id)):
        proj, q = code_delegate.take_fix(user.id)
        _log.info("🛠 修復計畫 %s → 專案 %s", _who(user), proj)
        await msg.reply_text("好，正在請 Agent 擬修復計畫，稍等…")
        the_plan = await asyncio.to_thread(code_delegate.plan, proj, q)
        owner_text = (f"📋 修復計畫（{proj}）— 由 {_who(user)} 的問題觸發\n"
                      f"問題：{q}\n\n{the_plan}\n\n"
                      f"（要執行修復就回「執行」，目前待執行：{proj}）")
        if is_owner(user.id):
            await _send_long(msg, owner_text)
        else:
            await _send_long_chat(context.bot, config.OWNER_CHAT_ID, owner_text)
            await msg.reply_text(f"已把修復計畫轉給 {config.OWNER_NAME} 審，他確認後會處理 🙏")
        code_delegate.remember_apply(
            config.OWNER_CHAT_ID, proj, q, the_plan,
            origin_chat=(None if is_owner(user.id) else msg.chat_id))
        return

    # 搭檔瀏覽網頁（借用已登入 Chrome）：僅 owner 私訊。
    # 放在程式委派 gate 之前——明確的「瀏覽」意圖優先，避免網域名（如 ka2ka.com）撞到同名專案被委派攔走。
    if config.BROWSE_ENABLED and is_owner(user.id) and not is_group:
        # 加白名單指令（優先於 _looks_like_browse 判斷）
        if text and text.strip().startswith("加白名單"):
            domain = text.strip()[len("加白名單"):].strip()
            if not domain:
                await msg.reply_text("請告訴我要加哪個網域，例如：加白名單 example.com")
            else:
                browse_allowlist.add(domain)
                await msg.reply_text(f"好，已把 {domain} 加進瀏覽白名單 ✅")
            return
        pend = _pending_browse.get(user.id)
        if pend and _is_confirm_reply(text):
            _pending_browse.pop(user.id, None)
            if time.time() - pend.get("ts", 0) > _BROWSE_PENDING_TTL_S:
                await msg.reply_text("這個確認等太久過期了，請重新跟我說一次要做什麼 🙏")
                return
            try:
                res = await asyncio.to_thread(browse_agent.resume, pend["pending"], _is_yes(text))
                await _deliver_browse(msg, context, res, user.id)
            except Exception as e:
                browse_tool.reset()
                await msg.reply_text("瀏覽器操作出狀況了，我先停手 🙏")
                await notify_owner_error(context.bot, e, where="瀏覽操作")
            return
        # 提議加白名單後，owner 自然回「好／幫我加入」即視為同意 → 加入並自動重試原任務。
        pa = _pending_allow.get(user.id)
        if pa:
            t = (text or "").strip()
            if any(w in t for w in ("好", "加", "可以", "yes", "ok", "OK", "行", "沒問題", "要")):
                _pending_allow.pop(user.id, None)
                browse_allowlist.add(pa["domain"])
                _browse_session[user.id] = time.time()
                await msg.reply_text(f"好，已把 {pa['domain']} 加進白名單 ✅，我這就去看…")
                await _run_browse(msg, context, user, pa["task"], pa["url"])
                return
            if any(w in t for w in ("不", "別", "取消", "算了", "no")):
                _pending_allow.pop(user.id, None)
                await msg.reply_text("好，那就先不加。")
                return
            _pending_allow.pop(user.id, None)            # 答非所問 → 清掉，當新指令往下走
        # 瀏覽模式：一旦開始瀏覽，後續訊息（截圖、點登入…）繼續走瀏覽工具，直到「結束瀏覽」或閒置逾時。
        in_session = (time.time() - _browse_session.get(user.id, 0)) < _BROWSE_SESSION_TTL_S
        if in_session and text and text.strip() in _BROWSE_STOP_WORDS:
            _browse_session.pop(user.id, None)
            await msg.reply_text("好，已結束瀏覽模式。")
            return
        if _looks_like_browse(text) or in_session:
            await msg.reply_text("好，我看一下，稍等…" if in_session
                                 else "好，我看一下，稍等…（已進入瀏覽模式：之後直接說要做什麼即可，例如「截圖」「點登入」；說「結束瀏覽」可離開）")
            _browse_session[user.id] = time.time()       # 開始／刷新瀏覽模式
            await _run_browse(msg, context, user, text, _extract_browse_url(text))
            return

    # 生圖：owner 私訊明確要圖時（bot 端關鍵字觸發，確定性；LLM 只負責把需求轉成 prompt）
    # 附圖/檔時跳過——這類訊息是「關於那張圖」，該走視覺問答；生圖看不到參考圖。
    if (config.IMAGE_GEN_ENABLED and is_owner(user.id)
            and not msg.photo and msg.document is None and _looks_like_image_request(text)):
        _log.info("🎨 生圖 %s：%s", _who(user), _preview(text))
        await msg.reply_text("好，幫你畫，稍等…")
        try:
            t0 = time.time()
            ctx = _recent_context(user.id)            # 帶近期對話，讓「三大天王」之類指涉解析正確
            prompt = await asyncio.to_thread(image_gen.craft_prompt, text, ctx)
            _log.info("🎨 prompt：%s", _preview(prompt) or "（空）")
            img = await asyncio.to_thread(image_gen.generate, prompt) if prompt else None
            if img:
                await context.bot.send_photo(chat_id=msg.chat_id, photo=BytesIO(img))
                _log.info("🎨 生圖完成（%d KB，%.1fs）", len(img) // 1024, time.time() - t0)
            else:
                await msg.reply_text("這次圖生不出來，稍後再試一次 🙏")
                _log.warning("🎨 生圖失敗（%.1fs，prompt=%s）", time.time() - t0, _preview(prompt) or "空")
        except Exception as e:
            await msg.reply_text("生圖出了點狀況，我先停手 🙏")
            await notify_owner_error(context.bot, e, where="生圖")
        return

    # 程式問題委派給 Agent（headless Claude Code）：owner 隨時／同事僅 owner 請假時；私訊、純文字
    # 附圖/檔時跳過——Agent 是純文字的、看不到圖；截圖+問題該走視覺問答（compose_reply 看得到圖）。
    if (text and not is_group and config.CODE_ROOT and not msg.photo and msg.document is None
            and (is_owner(user.id) or env_io.is_on_leave())):
        proj = code_delegate.classify(text)
        if proj:
            _log.info("🤖 程式委派 %s → 專案 %s", _who(user), proj)
            await msg.reply_text("收到，正在請該專案的 Agent 看一下，稍等…")
            ans = await asyncio.to_thread(code_delegate.ask, proj, text, datetime.now())
            await _send_long(msg, ans)
            memory.append(user.id, "user", text)
            memory.append(user.id, "assistant", ans)
            code_delegate.remember_fix(user.id, proj, text)
            await msg.reply_text(f"（需要修的話回「修復計畫」，我請 Agent 擬一份給 {config.OWNER_NAME} 審）")
            return

    group_context = group_memory.recent_transcript(chat.id) if is_group else None
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")
        _t0 = time.time()
        reply = await asyncio.to_thread(compose_reply, user.id, text, image_bytes, group_context,
                                        user.full_name)
        await msg.reply_text(reply)
        _log.info("💬 已回覆 %s（%d 字，%.1fs）", _who(user), len(reply or ""), time.time() - _t0)
        if is_group:
            group_memory.record(chat.id, config.ASSISTANT_NAME, reply)
    except Exception as e:
        _log.exception("compose_reply failed for user_id=%s", user.id)
        if llm.is_quota_error(e) and is_owner(user.id):    # 額度耗盡 → 給 owner 可操作的精準指引
            await msg.reply_text(llm.QUOTA_MSG)
        else:
            await msg.reply_text(f"抱歉，我這邊暫時有點狀況（可能是後端額度或連線問題），等一下再問我，或等 {config.OWNER_NAME} 回來確認 🙏")
            if not is_owner(user.id):                      # owner 本人已收道歉 → 不重複轟
                await notify_owner_error(context.bot, e, where="回覆訊息")


_ALERT_COOLDOWN_S = 300
_last_alert = {}                      # "ErrType|where" -> last sent ts（記憶體；重啟清空，可接受）


async def notify_owner_error(tg_bot, err, where="") -> None:
    """非預期例外時 DM owner：gated on OWNER_CHAT_ID、節流、best-effort、不碰記憶。"""
    if not config.OWNER_CHAT_ID:
        return
    key = f"{type(err).__name__}|{where}"
    now = time.time()
    if now - _last_alert.get(key, 0) < _ALERT_COOLDOWN_S:
        return                        # 同錯誤節流中 → 不重送
    _last_alert[key] = now
    text = (f"🚨 JAYVIS 出錯{('（' + where + '）') if where else ''}："
            f"{type(err).__name__}: {str(err)[:200]}\n詳見控制台 Log。")
    try:
        await tg_bot.send_message(chat_id=config.OWNER_CHAT_ID, text=text)
    except Exception:
        _log.warning("通知 owner 失敗（%s）", type(err).__name__)
    # 接著用「本部署設定的 LLM」自我診斷，再補一則可轉給作者的回報（best-effort、不阻塞迴圈、診斷失敗就算了）
    try:
        import diagnose
        report = await asyncio.to_thread(diagnose.diagnosis_report,
                                         f"{type(err).__name__}: {str(err)[:300]}", where)
        if report:
            await tg_bot.send_message(chat_id=config.OWNER_CHAT_ID, text=report)
    except Exception:
        pass


def reset_alerts():                   # 測試用
    _last_alert.clear()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """收斂錯誤日誌：與 Telegram 的網路暫斷只記一行（長輪詢會自動重試），
    其餘非預期例外才印完整堆疊，避免 log 被連線抖動洗成滿頁紅字。"""
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        _log.warning("🌐 與 Telegram 連線暫斷，已自動重試（%s）", type(err).__name__)
    else:
        _log.error("未處理例外：%r", err, exc_info=err)
        await notify_owner_error(context.bot, err, where="處理更新")


async def _leave_digest_loop():
    """背景檢查：請假結束就自動把期間彙整 DM 給 owner（啟動先跑一次→涵蓋結束後才重啟，之後每 6 小時）。"""
    while True:
        try:
            await asyncio.to_thread(leave_digest.check_and_send)
        except Exception:
            _log.exception("leave digest check failed")
        await asyncio.sleep(6 * 3600)


_digest_task = None


async def _post_init(application) -> None:
    global _digest_task
    _digest_task = asyncio.create_task(_leave_digest_loop())


async def _post_shutdown(application) -> None:
    """關閉（重啟/停止）時優雅取消背景任務，避免 asyncio『Task was destroyed but it is pending』。"""
    global _digest_task
    if _digest_task and not _digest_task.done():
        _digest_task.cancel()
        try:
            await _digest_task
        except (asyncio.CancelledError, Exception):
            pass


def main() -> None:
    if not config.TG_BOT_TOKEN:
        raise SystemExit("TG_BOT_TOKEN 未設定（請先跟 @BotFather 建 bot 並放進 .env）")
    global _lock_fp
    ok, _lock_fp = acquire_single_instance_lock()
    if not ok:
        _log.warning("偵測到已有 JAYVIS 實例在執行，這個多餘實例直接結束（避免 Telegram getUpdates Conflict）")
        sys.exit(0)
    app = Application.builder().token(config.TG_BOT_TOKEN).post_init(_post_init).post_shutdown(_post_shutdown).build()
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
        handle_message))
    app.add_error_handler(on_error)
    try:
        import memory
        migrated = memory.migrate_json()
        if migrated:
            _log.info("memory: 匯入舊對話 %d 筆", migrated)
    except Exception:
        _log.exception("memory.migrate_json failed")
    _log.info("✅ %s v%s ｜%s 啟動（long polling）｜allowlist=%d 人",
              config.APP_NAME, config.APP_VERSION, config.ASSISTANT_NAME, len(config.ALLOWLIST_USER_IDS))
    browse_tool.sweep_tmp()
    if config.ACTIONS_ENABLED:
        import threading
        threading.Thread(target=agent.warm_calendars, daemon=True).start()   # 預熱日曆快取，避免冷快取逾時
    app.run_polling()


if __name__ == "__main__":
    main()
