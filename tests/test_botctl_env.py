import os

from panel import botctl


def test_bot_env_overrides_inherited_with_dotenv(tmp_path, monkeypatch):
    """bot 子行程要用當前 .env 蓋過繼承來的舊環境變數（否則重啟後仍跑舊模型）。"""
    (tmp_path / ".env").write_text(
        "MODEL_GENERAL=qwen3-coder:30b\nMODEL_CODE=qwen3-coder:30b\n", encoding="utf-8")
    monkeypatch.setattr(botctl, "ROOT", tmp_path)
    monkeypatch.setenv("MODEL_GENERAL", "qwen2.5-coder:7b")   # 模擬面板繼承的舊值
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))    # 確保仍帶基本環境

    env = botctl._bot_env()
    assert env["MODEL_GENERAL"] == "qwen3-coder:30b"          # .env 覆蓋繼承值
    assert env["MODEL_CODE"] == "qwen3-coder:30b"
    assert "PATH" in env                                       # 其餘繼承環境保留
