import asyncio
import logging
import re
import time
from io import BytesIO

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
import browse_agent
import browse_tool
import browse_allowlist
import code_delegate
import memory
import persona
from assistant import compose_reply
from panel import env_io

logging.basicConfig(level=logging.INFO)
# 第三方 INFO 噪音：httpx 每次 long-poll 都印一行（且 URL 內含 bot token！）、
# telegram.ext 的 Application started/stopping/stop() complete 生命週期、apscheduler 排程。
# 壓到 WARNING：保留真正的警告/錯誤，砍掉每次重啟的洗版與 token 落地 bot.log。
_QUIET_LOGGERS = ("httpx", "httpcore", "telegram", "apscheduler")
for _n in _QUIET_LOGGERS:
    logging.getLogger(_n).setLevel(logging.WARNING)
_log = logging.getLogger("jayvis")

_pending_browse = {}                  # owner_id -> {"pending": dict}

_BROWSE_HINT = ("瀏覽", "幫我看 http", "看一下 http", "打開網", "查網", "逛", "網頁", "後台")


def _looks_like_browse(text: str) -> bool:
    t = text or ""
    if "http://" in t or "https://" in t:
        return True
    return any(h in t for h in _BROWSE_HINT)


def _is_confirm_reply(text: str) -> bool:
    return (text or "").strip() in ("確認", "好", "可以", "yes", "y", "取消", "不要", "no", "n")


def _is_yes(text: str) -> bool:
    return (text or "").strip() in ("確認", "好", "可以", "yes", "y")


async def _deliver_browse(msg, context, res, uid) -> None:
    from io import BytesIO
    if res.status == "pending":
        _pending_browse[uid] = {"pending": res.pending}
        await msg.reply_text(f"⚠️ 這個動作會改東西：{res.summary}\n要我執行嗎？回「確認」或「取消」。")
    else:
        await _send_long(msg, res.summary or "（沒有內容）")
    if res.screenshot:
        await context.bot.send_photo(chat_id=msg.chat_id, photo=BytesIO(res.screenshot))


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
        # 一律記錄群組對話（含非白名單者）建立完整脈絡
        speaker = config.ALLOWLIST_ALIASES.get(user.id) or user.full_name or str(user.id)
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
    if (not is_group and config.MEDIA_ENABLED and is_owner(user.id)
            and text and not msg.photo and msg.document is None
            and agent.looks_like_media_request(text) and agent.has_remembered_media()):
        result = await asyncio.to_thread(agent.handle_media_followup, text, datetime.now())
        if result.file is not None:
            _log.info("🖼 媒體（跟進上一張圖）→ %s", result.filename)
            await msg.reply_document(document=BytesIO(result.file), filename=result.filename, caption=result.note)
        else:
            await msg.reply_text(result.message)
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
            return

    # owner 媒體工具（去背/轉檔/調尺寸）：私訊 + owner + 啟用 + 帶檔案才走。
    # 文件一律進；照片需有說明（caption），讓無說明的照片仍走一般視覺對話。
    if (not is_group and config.MEDIA_ENABLED and is_owner(user.id)
            and (msg.document is not None or (msg.photo and text))):
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
        agent.remember_media(raw, fname)   # 記住，供之後純文字跟進指令套用
        result = await asyncio.to_thread(agent.handle_media, text, raw, fname, datetime.now())
        if result.file is not None:
            _log.info("🖼 媒體 %s → %s", fname, result.filename)
            cap = result.note
            if not msg.document:   # 來源是被壓過的 photo → 提醒原圖品質
                cap = ((cap + "\n") if cap else "") + "（這是 Telegram 壓過的圖；想要原畫質/去背更乾淨，請用「檔案」方式傳原圖。）"
            await msg.reply_document(document=BytesIO(result.file), filename=result.filename, caption=cap)
        else:
            await msg.reply_text(result.message)
        return

    image_bytes = None
    if msg.photo:
        f = await msg.photo[-1].get_file()
        ba = await f.download_as_bytearray()
        image_bytes = bytes(ba)
        if config.MEDIA_ENABLED and is_owner(user.id):
            agent.remember_media(image_bytes, "photo.jpg")   # 無說明的照片也記住，供跟進指令

    if not text and image_bytes is None:
        await msg.reply_text(f"我是 {config.ASSISTANT_NAME}，{config.OWNER_NAME} 請假中；有問題可以直接打給我～")
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

    # 程式問題委派給 Agent（headless Claude Code）：owner 隨時／同事僅 owner 請假時；私訊、文字
    if (text and not is_group and config.CODE_ROOT
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

    # 助理瀏覽網頁（借用已登入 Chrome）：僅 owner 私訊；讀自動、寫入前確認
    if config.BROWSE_ENABLED and is_owner(user.id) and not is_group:
        pend = _pending_browse.get(user.id)
        if pend and _is_confirm_reply(text):
            _pending_browse.pop(user.id, None)
            try:
                res = await asyncio.to_thread(browse_agent.resume, pend["pending"], _is_yes(text))
                await _deliver_browse(msg, context, res, user.id)
            except Exception as e:
                await msg.reply_text("瀏覽器操作出狀況了，我先停手 🙏")
                await notify_owner_error(context.bot, e, where="瀏覽操作")
            return
        if _looks_like_browse(text):
            await msg.reply_text("好，我去看一下，稍等…")
            try:
                res = await asyncio.to_thread(browse_agent.run, text, None)
                await _deliver_browse(msg, context, res, user.id)
            except browse_tool.BrowseUnavailable:
                await msg.reply_text(
                    "Chrome 沒開遠端偵錯。請用：\n"
                    "open -a 'Google Chrome' --args --remote-debugging-port=9222\n"
                    "啟動後再試一次 🙏")
            except browse_tool.NotAllowed as e:
                await msg.reply_text(f"「{e}」不在我的瀏覽白名單，要我加進去嗎？（回「加白名單 <網域>」）")
            except Exception as e:
                await msg.reply_text("瀏覽出了點狀況，我先停手 🙏")
                await notify_owner_error(context.bot, e, where="瀏覽網頁")
            return

    group_context = group_memory.recent_transcript(chat.id) if is_group else None
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")
        reply = await asyncio.to_thread(compose_reply, user.id, text, image_bytes, group_context,
                                        user.full_name)
        await msg.reply_text(reply)
        _log.info("💬 已回覆 %s（%d 字）", _who(user), len(reply or ""))
        if is_group:
            group_memory.record(chat.id, config.ASSISTANT_NAME, reply)
    except Exception as e:
        _log.exception("compose_reply failed for user_id=%s", user.id)
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


def main() -> None:
    if not config.TG_BOT_TOKEN:
        raise SystemExit("TG_BOT_TOKEN 未設定（請先跟 @BotFather 建 bot 並放進 .env）")
    app = Application.builder().token(config.TG_BOT_TOKEN).build()
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
