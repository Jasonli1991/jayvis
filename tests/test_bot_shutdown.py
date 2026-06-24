"""bot 關閉時優雅取消背景任務的回歸測試。

複現問題：_post_init 用 asyncio.create_task(_leave_digest_loop()) fire-and-forget、關閉時沒取消，
重啟/停止（SIGTERM 優雅關閉）時事件迴圈收掉、任務仍 pending → asyncio『Task was destroyed but it is pending』。
修法：留任務參考，post_shutdown 時 cancel + await。
"""
import asyncio

import bot


def test_post_shutdown_cancels_pending_digest_task():
    async def run():
        bot._digest_task = asyncio.create_task(asyncio.sleep(3600))   # 模擬背景任務 pending
        await asyncio.sleep(0)                                        # 讓任務真的排程
        await bot._post_shutdown(None)                               # 關閉鉤子
        assert bot._digest_task.cancelled()                          # 已優雅取消、不會 pending 被銷毀
    asyncio.run(run())


def test_post_shutdown_noop_when_no_task():
    async def run():
        bot._digest_task = None
        await bot._post_shutdown(None)                               # 不應拋錯
    asyncio.run(run())
