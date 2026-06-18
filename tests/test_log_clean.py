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


_TRACEBACK_LOG = "\n".join([
    'INFO:jayvis:處理訊息',
    'ERROR:jayvis:compose_reply failed for user_id=6803',
    'Traceback (most recent call last):',
    '  File "/x/llm.py", line 78, in _gen_google',
    '    resp = client.generate_content(...)',
    '  File "/x/genai/_api_client.py", line 1381, in _request_once',
    '    errors.APIError.raise_for_response(response)',
    "google.genai.errors.ClientError: 404 NOT_FOUND. {'error': {'code': 404}}",
    'INFO:jayvis:下一則',
    '',
])


def test_tail_log_clean_collapses_traceback(tmp_path, monkeypatch):
    log = tmp_path / "bot.log"
    log.write_text(_TRACEBACK_LOG, encoding="utf-8")
    monkeypatch.setattr(botctl, "LOG_FILE", log)
    out = botctl.tail_log(50, clean=True)
    assert "Traceback (most recent call last):" not in out   # 整段收摺
    assert 'File "/x/llm.py"' not in out                      # 框架行不顯示
    assert out.count("404 NOT_FOUND") == 1                    # 重點保留、只剩一行
    assert "compose_reply failed" in out                     # 前一行 context 仍在
    assert "下一則" in out                                    # 收摺後續行不受影響


def test_tail_log_raw_keeps_traceback(tmp_path, monkeypatch):
    log = tmp_path / "bot.log"
    log.write_text(_TRACEBACK_LOG, encoding="utf-8")
    monkeypatch.setattr(botctl, "LOG_FILE", log)
    raw = botctl.tail_log(50)                                 # 預設（檔案備查）不收摺
    assert "Traceback (most recent call last):" in raw and 'File "/x/llm.py"' in raw
