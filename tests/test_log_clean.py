from panel import botctl


def test_tail_log_clean_filters_noise(tmp_path, monkeypatch):
    log = tmp_path / "bot.log"
    log.write_text("\n".join([
        'INFO:httpx:HTTP Request: POST https://api.telegram.org/botXXX:TOKEN/getUpdates "200 OK"',
        'INFO:llm:LLM call: model=qwen3:8b provider=openai',
        'Batches: 100%|####| 1/1',
        'INFO:sentence_transformers.SentenceTransformer:Use pytorch device: mps',
        'INFO:jayvis:✅ 啟動',
        '',
    ]), encoding="utf-8")
    monkeypatch.setattr(botctl, "LOG_FILE", log)
    out = botctl.tail_log(50, clean=True)
    assert "api.telegram.org" not in out      # 噪音 + token 洩漏一併濾掉
    assert "TOKEN" not in out
    assert "Batches" not in out
    assert "sentence_transformers" not in out
    assert "LLM call" in out and "啟動" in out  # 訊號保留


def test_tail_log_default_unfiltered(tmp_path, monkeypatch):
    log = tmp_path / "bot.log"
    log.write_text("api.telegram.org line\nreal line\n", encoding="utf-8")
    monkeypatch.setattr(botctl, "LOG_FILE", log)
    assert "api.telegram.org" in botctl.tail_log(50)   # 預設不過濾（相容）
