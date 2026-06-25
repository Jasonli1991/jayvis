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


def test_render_persona_includes_character():
    assert "你自己的角色" in PERSONA and "ENFP" in PERSONA       # 角色已併入同事人設


def test_character_block_fixed_traits_hardcoded_creator(monkeypatch):
    # owner/名稱參數化（多租戶安全）；創造者寫死＝Jason；沒有「對 owner 的看法」；守住不編造守則
    monkeypatch.setattr(persona, "load_profile", lambda: {"owner_name": "Eric", "assistant_name": "BOB"})
    b = persona.character_block()
    assert "3月14日" in b and "ENFP" in b and "雙魚" in b        # 固定特徵
    assert "創造者 Jason" in b                                    # 創造者寫死＝Jason
    assert "BOB" in b and "Eric" in b                            # 名稱/owner 參數化
    assert "對 Eric 的看法" not in b and "對主人的看法" not in b   # 不做「對 owner 的看法」
    assert "被問到才" in b                                        # 守則：被問到才分享、不編造
    assert "名字由來" not in b                                    # 改名（非 JAYVIS）→ 縮寫不適用、不顯示


def test_character_block_name_origin_for_jayvis(monkeypatch):
    # 名字未改（JAYVIS）→ 帶名字由來：J=Jason 寫死、Your=主人
    monkeypatch.setattr(persona, "load_profile", lambda: {"owner_name": "Jason", "assistant_name": "JAYVIS"})
    b = persona.character_block()
    assert "名字由來" in b and "Sidekick" in b and "Jason's AI" in b
