import persona

PERSONA = persona.render_persona()


def test_persona_is_assistant_not_impersonation():
    # 搭檔身份應出現在 identity 區塊（owner_name 取自 owner_profile(.example).json）
    assert "的 AI 搭檔" in PERSONA or "的搭檔" in PERSONA


def test_persona_does_not_forbid_revealing_ai():
    # 舊的冒名規則必須移除
    assert "不要透露自己是 AI" not in PERSONA


def test_persona_keeps_grounding_rule():
    assert "絕不自行編造" in PERSONA
