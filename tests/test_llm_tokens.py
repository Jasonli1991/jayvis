"""generate 會把每次 LLM 呼叫的 token（in/out/共）記進 log（即時 log 看得到），且仍回傳文字。"""
import logging

import llm


def test_generate_logs_token_usage_and_returns_text(monkeypatch, caplog):
    monkeypatch.setattr(llm, "_provider_of", lambda m: "google")
    monkeypatch.setattr(llm, "_gen_google", lambda **k: ("嗨，這是回覆", 120, 45))
    with caplog.at_level(logging.INFO, logger="llm"):
        out = llm.generate("gemini-2.5-flash", "sys", [{"role": "user", "content": "hi"}])
    assert out == "嗨，這是回覆"                                  # 公開介面仍回字串
    msgs = [r.getMessage() for r in caplog.records]
    assert any("token in 120 / out 45 / 共 165" in m for m in msgs)   # token 有記進 log
