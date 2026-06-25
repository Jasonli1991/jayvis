import json
from pathlib import Path

_DIR = Path(__file__).parent / "prompts"
PROFILE_PATH = _DIR / "owner_profile.json"
PROFILE_EXAMPLE_PATH = _DIR / "owner_profile.example.json"
TEMPLATE_PATH = _DIR / "persona_template.md"


def load_profile() -> dict:
    # 使用者透過控制台寫入 owner_profile.json；未設定時退回 .example 範本，再退回空 dict。
    path = PROFILE_PATH if PROFILE_PATH.exists() else PROFILE_EXAMPLE_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _identity_block(p: dict) -> str:
    name = p.get("owner_name", "")
    lines = [
        f"你是 **{name} 的 AI 搭檔**。{name} 是{p.get('company', '')}的{p.get('title', '')}。"
        "你代表他、用他的工作記憶，協助同事查詢與回答問題。"
        "**你誠實表明自己是搭檔，不假冒本人。**",
    ]
    projs = [x for x in (p.get("projects") or []) if x.get("name")]
    if projs:
        items = "、".join(
            f"{x['name']}（{x['desc']}）" if x.get("desc") else x["name"] for x in projs
        )
        lines.append(f"{name} 主要負責：{items}。")
    team = [x for x in (p.get("team") or []) if x.get("name")]
    if team:
        items = "、".join(
            f"{x['name']}（{x['role']}）" if x.get("role") else x["name"] for x in team
        )
        lines.append(f"團隊：{items}。")
    for b in p.get("bosses") or []:
        if not b.get("name"):
            continue
        note = f"——{b['note']}" if b.get("note") else ""
        lines.append(f"老闆是 {b['name']}{note}".replace("{owner_name}", name))
    return "\n".join(lines)


def roster_block() -> str:
    """owner 模式用：精簡的團隊／老闆／專案名冊（含角色職責），供 JAYVIS 回答
    「某人是誰／負責什麼」「專案歸屬」這類問題。純事實、不含對外代言框架；無資料回 ''。
    每次呼叫即時讀 owner_profile.json（面板改完不必重啟 bot 即生效）。"""
    p = load_profile()
    name = p.get("owner_name", "")
    lines = []
    projs = [x for x in (p.get("projects") or []) if x.get("name")]
    if projs:
        items = "、".join(f"{x['name']}（{x['desc']}）" if x.get("desc") else x["name"] for x in projs)
        lines.append(f"- 專案：{items}")
    team = [x for x in (p.get("team") or []) if x.get("name")]
    if team:
        items = "、".join(f"{x['name']}（{x['role']}）" if x.get("role") else x["name"] for x in team)
        lines.append(f"- 團隊：{items}")
    bosses = p.get("bosses") or []
    if bosses:
        items = "、".join((f"{b['name']}（{b['note']}）" if b.get("note") else b["name"]).replace("{owner_name}", name)
                          for b in bosses if b.get("name"))
        if items:
            lines.append(f"- 老闆：{items}")
    if not lines:
        return ""
    return ("## 你認識的人與專案（供你回答人員角色／職責、專案歸屬；非即時動態，"
            "最新進度以知識庫／專案狀態為準）\n" + "\n".join(lines))


def render_persona() -> str:
    p = load_profile()
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = text.replace("{{identity}}", _identity_block(p))
    text = text.replace("{{routing}}", p.get("routing", ""))
    text = text.replace("{{assistant_name}}", p.get("assistant_name", ""))
    text = text.replace("{{owner_name}}", p.get("owner_name", ""))
    return text
