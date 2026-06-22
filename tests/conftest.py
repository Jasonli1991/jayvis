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


@pytest.fixture()
def conn(tmp_path):
    c = get_conn(str(tmp_path / "kb.sqlite"))
    apply_schema(c)
    yield c
    c.close()
