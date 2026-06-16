"""bot.py 把第三方 INFO 噪音壓到 WARNING：
- httpx 每次 long-poll 會把含 bot token 的 URL 印成 INFO → 必須靜音（token 不可落地 bot.log）。
- telegram.ext 的 Application started/stopping/stop() complete 生命週期洗版 → 靜音。
- 我們自己的 jayvis 啟動行與任何 WARNING/ERROR 仍要留著。
"""
import logging

import bot  # 匯入即套用 logging 設定（與 test_bot_allowlist 等相同模式）


def test_noisy_loggers_muted_to_warning():
    for name in ("httpx", "httpcore", "telegram", "apscheduler"):
        lg = logging.getLogger(name)
        assert lg.getEffectiveLevel() >= logging.WARNING, f"{name} 應被壓到 WARNING 以上"


def test_telegram_ext_lifecycle_silenced():
    """'Application started/stopping/stop() complete' 來自 telegram.ext.Application，INFO 應被擋。"""
    lg = logging.getLogger("telegram.ext.Application")
    assert not lg.isEnabledFor(logging.INFO)


def test_httpx_info_silenced_but_warning_survives():
    """httpx INFO（含 token 的 HTTP Request 行）要擋，但 WARNING/ERROR 仍要能出。"""
    lg = logging.getLogger("httpx")
    assert not lg.isEnabledFor(logging.INFO)
    assert lg.isEnabledFor(logging.WARNING)


def test_our_logger_not_muted():
    """jayvis 不能被一起靜音：不在靜音清單、也沒被顯式提級，
    所以它跟著 root（basicConfig=INFO）走 → 啟動行照印。
    （root 等級這裡顯式設 INFO 還原真實情境，避免被 pytest 的 root=WARNING 干擾。）"""
    assert "jayvis" not in bot._QUIET_LOGGERS
    lg = logging.getLogger("jayvis")
    assert lg.level == logging.NOTSET            # 我們沒對它 setLevel
    root = logging.getLogger()
    saved = root.level
    root.setLevel(logging.INFO)
    try:
        assert lg.isEnabledFor(logging.INFO)
    finally:
        root.setLevel(saved)
