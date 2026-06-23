"""botctl.preflight_errors 的測試：啟動前檢查最低必要設定（Bot Token + 一般模型可用）。

對應全新使用者「什麼都沒填就按啟動」的情境：應擋下並回清楚的缺項，而非讓 bot 子行程閃退。
preflight 現讀傳入的 .env（不靠面板可能過時的 config.*），模型可用性比照 llm._provider_of 路由。
"""
from panel import botctl


def _env(tmp_path, **kv) -> str:
    p = tmp_path / ".env"
    p.write_text("".join(f"{k}={v}\n" for k, v in kv.items()), encoding="utf-8")
    return str(p)


def test_empty_env_reports_token_and_model(tmp_path):
    # 全空 .env：MODEL_GENERAL 退回 gemini 預設、無金鑰 → token + 模型兩個問題
    probs = botctl.preflight_errors(_env(tmp_path))
    assert len(probs) == 2
    assert any("Token" in p for p in probs)
    assert any("模型" in p for p in probs)


def test_token_and_gemini_key_ok(tmp_path):
    probs = botctl.preflight_errors(
        _env(tmp_path, TG_BOT_TOKEN="123:abc", MODEL_GENERAL="gemini-2.5-flash", GEMINI_API_KEY="g"))
    assert probs == []


def test_token_only_still_flags_model(tmp_path):
    probs = botctl.preflight_errors(_env(tmp_path, TG_BOT_TOKEN="123:abc", MODEL_GENERAL="gemini-2.5-flash"))
    assert len(probs) == 1 and "模型" in probs[0]


def test_claude_model_needs_anthropic_key(tmp_path):
    bad = botctl.preflight_errors(_env(tmp_path, TG_BOT_TOKEN="t", MODEL_GENERAL="claude-opus-4-8"))
    assert len(bad) == 1 and "Anthropic" in bad[0]
    ok = botctl.preflight_errors(
        _env(tmp_path, TG_BOT_TOKEN="t", MODEL_GENERAL="claude-opus-4-8", ANTHROPIC_API_KEY="a"))
    assert ok == []


def test_gpt_model_needs_openai_key_or_base_url(tmp_path):
    bad = botctl.preflight_errors(_env(tmp_path, TG_BOT_TOKEN="t", MODEL_GENERAL="gpt-4o"))
    assert len(bad) == 1
    assert botctl.preflight_errors(
        _env(tmp_path, TG_BOT_TOKEN="t", MODEL_GENERAL="gpt-4o", OPENAI_API_KEY="k")) == []


def test_local_model_with_base_url_needs_no_key(tmp_path):
    # 未知前綴（本地 Ollama 等）+ 有相容端點 → 免金鑰即可
    probs = botctl.preflight_errors(
        _env(tmp_path, TG_BOT_TOKEN="t", MODEL_GENERAL="gemma:12b", OPENAI_BASE_URL="http://localhost:11434/v1"))
    assert probs == []


def test_missing_token_only(tmp_path):
    probs = botctl.preflight_errors(
        _env(tmp_path, MODEL_GENERAL="gemini-2.5-flash", GEMINI_API_KEY="g"))
    assert len(probs) == 1 and "Token" in probs[0]
