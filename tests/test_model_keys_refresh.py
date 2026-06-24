"""存金鑰後免重啟面板即生效的回歸測試。

複現問題：面板「模型」卡存金鑰＝寫進 .env，但跑著的面板 config 是啟動時載入的（load_dotenv 不重讀），
故 /api/provider-models 用舊的空金鑰列模型 → 下拉永遠空。修法：列模型前 config.reload_runtime_keys()
即時刷新金鑰、llm.reset_clients() 清掉用舊金鑰建的快取 client。
"""
import config
import llm

_RUNTIME_KEYS = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                 "OPENAI_BASE_URL", "GCP_PROJECT", "GCP_LOCATION", "TAVILY_API_KEY",
                 "MODEL_GENERAL", "MODEL_CODE"]


def test_reload_runtime_keys_reads_env(tmp_path):
    saved = {k: getattr(config, k) for k in _RUNTIME_KEYS}   # 測完還原，避免污染其他測試
    try:
        p = tmp_path / ".env"
        p.write_text("GEMINI_API_KEY=g-xyz\nOPENAI_BASE_URL=http://localhost:11434/v1\n"
                     "MODEL_GENERAL=gpt-4o\n", encoding="utf-8")
        config.reload_runtime_keys(str(p))
        assert config.GEMINI_API_KEY == "g-xyz"              # .env 有 → 刷進來
        assert config.OPENAI_BASE_URL == "http://localhost:11434/v1"
        assert config.ANTHROPIC_API_KEY == ""                # .env 沒有 → 空
        assert config.GCP_LOCATION == "global"               # 預設
        assert config.MODEL_GENERAL == "gpt-4o"              # 模型名也刷新
        assert config.MODEL_CODE == "gemini-2.5-pro"         # .env 沒有 → 退回預設（非空字串）
    finally:
        for k, v in saved.items():
            setattr(config, k, v)


def test_reset_clients_clears_cache():
    llm._clients["dummy"] = object()
    llm.reset_clients()
    assert llm._clients == {}
