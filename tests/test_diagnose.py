"""LLM 自我診斷：模型錯誤略過、LLM 呼叫、回報格式、以及 notify_owner_error 會補送診斷。
全程本機、用本機 LLM、結果只給本機 owner（不對外回報）。"""
import asyncio

import config
import diagnose


def test_is_model_error():
    assert diagnose.is_model_error("RateLimitError: 429 quota exceeded")
    assert diagnose.is_model_error("AuthError: invalid api key")
    assert not diagnose.is_model_error("KeyError: 'calendar'")
    assert not diagnose.is_model_error("Conflict: terminated by other getUpdates")


def test_build_diagnosis_calls_local_llm(monkeypatch):
    seen = {}

    def fake_gen(model, system, messages, max_output_tokens=500):
        seen["model"] = model
        seen["user"] = messages[0]["content"]
        return "  【可能原因】X\n【建議】填金鑰  "

    monkeypatch.setattr(diagnose, "generate", fake_gen)
    out = diagnose.build_diagnosis("KeyError: x", "INFO:jayvis:啟動")
    assert out == "【可能原因】X\n【建議】填金鑰"                 # 去頭尾空白
    assert seen["model"] == config.MODEL_GENERAL                # 用本部署設定的模型
    assert "KeyError: x" in seen["user"] and "INFO:jayvis" in seen["user"]


def test_build_diagnosis_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(diagnose, "generate", lambda **k: (_ for _ in ()).throw(RuntimeError("llm down")))
    assert diagnose.build_diagnosis("KeyError", "log") == ""    # 失敗不丟例外、回空


def test_diagnosis_report_skips_model_errors(monkeypatch):
    called = []
    monkeypatch.setattr(diagnose, "generate", lambda **k: called.append(1) or "x")
    assert diagnose.diagnosis_report("RateLimitError: 429 quota", "回覆訊息") == ""
    assert called == []                                          # 模型本身有問題 → 根本不呼叫模型


def test_diagnosis_report_formats_for_forwarding(monkeypatch):
    monkeypatch.setattr(diagnose, "generate",
                        lambda model, system, messages, max_output_tokens=500: "【可能原因】沒設行事曆")
    from panel import botctl
    monkeypatch.setattr(botctl, "tail_log", lambda n=40, clean=True: "INFO:jayvis:啟動")
    rep = diagnose.diagnosis_report("KeyError: 'calendar'", "行事曆")
    assert "JAYVIS 自我診斷" in rep and "可直接轉給作者" in rep   # 方便 owner 轉發
    assert "KeyError: 'calendar'" in rep and "【可能原因】沒設行事曆" in rep
    assert f"v{config.APP_VERSION}" in rep and "行事曆" in rep


def test_notify_owner_error_sends_alert_then_diagnosis(monkeypatch):
    import bot
    monkeypatch.setattr(config, "OWNER_CHAT_ID", 123)
    bot.reset_alerts()
    monkeypatch.setattr(diagnose, "diagnosis_report", lambda summ, where="": "🔍 診斷：建議填金鑰")
    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text):
            sent.append(text)

    asyncio.run(bot.notify_owner_error(FakeBot(), KeyError("calendar"), where="行事曆"))
    assert any("🚨 JAYVIS 出錯" in t for t in sent)              # 先即時簡訊
    assert any("🔍 診斷" in t for t in sent)                     # 再補 LLM 診斷回報
