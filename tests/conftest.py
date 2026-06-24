import pytest

from db.connection import get_conn, apply_schema


@pytest.fixture(autouse=True)
def _isolate_kb(tmp_path, monkeypatch):
    """每個測試把 KB 導到暫存 DB：避免測試經由 memory.append(conn=None)
    （compose_reply / agent._execute / handle_media 的記錄路徑）寫進正式記憶庫。
    同時把 group_memory 的 JSON 檔導到暫存：handle_message 在群組分支會
    group_memory.record(...)，否則測試會污染正式的 ~/.n/group_conversations.json。"""
    import config
    import memory
    import group_memory
    monkeypatch.setattr(config, "KB_PATH", str(tmp_path / "isolated-kb.sqlite"))
    monkeypatch.setattr(group_memory, "GROUP_PATH", tmp_path / "group_conversations.json")
    memory._schema_ready.clear()
    yield
    memory._schema_ready.clear()


@pytest.fixture(autouse=True)
def _no_real_diagnosis_llm(monkeypatch):
    """預設 stub 掉自我診斷的 LLM 呼叫：notify_owner_error 出錯時會 diagnose（呼叫真模型），
    測試機可能有真金鑰 → 會打真 API、變慢、有成本。test_diagnose 自行覆寫 diagnose.generate。"""
    import diagnose
    monkeypatch.setattr(diagnose, "generate", lambda *a, **k: "")
    yield


@pytest.fixture()
def conn(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(c)
    yield c
    c.close()
