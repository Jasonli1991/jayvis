"""動作分支會把整段互動記進對話脈絡，讓 JAYVIS 下一輪記得自己剛做了什麼（不「換了個人」）。
動作路徑不走 compose_reply，過去只有寫入型動作會記 kind="action"（recent() 排除），
唯讀查詢與確認流程則完全沒記 → 這裡確保 user 觸發訊息 + 回覆都進 recent()。"""
import asyncio
from types import SimpleNamespace

import agent
import bot
import config
import memory


def _msg(text):
    sent = {}

    async def reply_text(t):
        sent.update(text=t)

    m = SimpleNamespace(text=text, caption=None, document=None, photo=[],
                        chat=SimpleNamespace(id=1, type="private", title=None), chat_id=1,
                        reply_text=reply_text)
    return m, sent


def _update_ctx(msg, uid=777):
    update = SimpleNamespace(effective_message=msg,
                            effective_user=SimpleNamespace(id=uid, full_name="J"),
                            effective_chat=msg.chat)

    async def send_chat_action(**k):
        pass

    ctx = SimpleNamespace(bot=SimpleNamespace(username="bot", send_chat_action=send_chat_action))
    return update, ctx


def _owner_action_env(monkeypatch):
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 777)
    monkeypatch.setattr(config, "OWNER_NAME", "Jason")
    monkeypatch.setattr(config, "ALLOWLIST_USER_IDS", {777})
    monkeypatch.setattr(config, "ACTIONS_ENABLED", True)
    monkeypatch.setattr(config, "EMAIL_ENABLED", False)
    monkeypatch.setattr(config, "MEDIA_ENABLED", False)
    monkeypatch.setattr(config, "BROWSE_ENABLED", False)
    monkeypatch.setattr(config, "IMAGE_GEN_ENABLED", False)
    monkeypatch.setattr(config, "CODE_ROOT", "")


def test_action_branch_records_turns_into_recent(monkeypatch):
    _owner_action_env(monkeypatch)
    monkeypatch.setattr(agent, "handle", lambda *a, **k: "已新增『與 Max 開會』6/25 15:00 📅")
    msg, sent = _msg("幫我約 6/25 下午三點跟 Max 開會")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["text"].startswith("已新增")
    h = memory.recent(777)                                  # conn=None → 走隔離 KB
    assert h == [{"role": "user", "content": "幫我約 6/25 下午三點跟 Max 開會"},
                 {"role": "assistant", "content": "已新增『與 Max 開會』6/25 15:00 📅"}]


def test_readonly_action_query_also_remembered(monkeypatch):
    # 唯讀查詢（不產生 kind="action"）也要進 recent()，否則「第二個改到下午」會找不到脈絡
    _owner_action_env(monkeypatch)
    monkeypatch.setattr(agent, "handle", lambda *a, **k: "今天有：1. 午餐 12:00  2. 開會 15:00")
    msg, sent = _msg("今天有什麼行程")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    h = memory.recent(777)
    assert h[0] == {"role": "user", "content": "今天有什麼行程"}
    assert h[1]["role"] == "assistant" and "開會 15:00" in h[1]["content"]


def test_non_action_falls_through_to_compose_no_double_record(monkeypatch):
    # agent.handle 回 None（非動作）→ 不在動作分支記，交給 compose_reply 記（避免重複）
    _owner_action_env(monkeypatch)
    monkeypatch.setattr(agent, "handle", lambda *a, **k: None)
    monkeypatch.setattr(bot, "compose_reply", lambda *a, **k: "一般聊天回覆")
    msg, sent = _msg("你今天過得如何")
    update, ctx = _update_ctx(msg)
    asyncio.run(bot.handle_message(update, ctx))
    assert sent["text"] == "一般聊天回覆"
    # compose_reply 被 mock 掉（不會記），動作分支也沒記 → recent 為空，證明沒有重複記錄
    assert memory.recent(777) == []
