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
    projs = p.get("projects") or []
    if projs:
        items = "、".join(
            f"{x['name']}（{x['desc']}）" if x.get("desc") else x["name"] for x in projs
        )
        lines.append(f"{name} 主要負責：{items}。")
    team = p.get("team") or []
    if team:
        items = "、".join(
            f"{x['name']}（{x['role']}）" if x.get("role") else x["name"] for x in team
        )
        lines.append(f"團隊：{items}。")
    for b in p.get("bosses") or []:
        note = f"——{b['note']}" if b.get("note") else ""
        lines.append(f"老闆是 {b['name']}{note}".replace("{owner_name}", name))
    return "\n".join(lines)


def render_persona() -> str:
    p = load_profile()
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = text.replace("{{identity}}", _identity_block(p))
    text = text.replace("{{routing}}", p.get("routing", ""))
    text = text.replace("{{assistant_name}}", p.get("assistant_name", ""))
    text = text.replace("{{owner_name}}", p.get("owner_name", ""))
    return text
