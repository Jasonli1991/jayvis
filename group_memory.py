import json
from pathlib import Path

GROUP_PATH = Path.home() / ".n" / "group_conversations.json"
MAX_MSGS = 10     # 每群保留最近幾則訊息
MAX_TEXT = 400    # 每則文字截斷長度（避免 context 爆）


def _load() -> dict:
    if GROUP_PATH.exists():
        try:
            return json.loads(GROUP_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict) -> None:
    GROUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    GROUP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record(chat_id: int, speaker: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "…"
    data = _load()
    key = str(chat_id)
    data.setdefault(key, []).append({"speaker": speaker, "text": text})
    data[key] = data[key][-MAX_MSGS:]
    _save(data)


def recent_transcript(chat_id: int, n: int = MAX_MSGS) -> str:
    msgs = _load().get(str(chat_id), [])[-n:]
    return "\n".join(f"{m['speaker']}：{m['text']}" for m in msgs)


def clear(chat_id: int) -> None:
    data = _load()
    data.pop(str(chat_id), None)
    _save(data)


def clear_all() -> None:
    _save({})
