import assistant


def test_build_system_prompt_includes_folder_legend():
    s = assistant._build_system_prompt("某知識片段", "")
    assert "資料夾語意" in s and "問答紀錄" in s
    assert "某知識片段" in s


def test_build_owner_system_includes_folder_legend():
    s = assistant.build_owner_system("某知識片段", "")
    assert "資料夾語意" in s and "某知識片段" in s


def test_no_legend_without_rag():
    assert "資料夾語意" not in assistant._build_system_prompt("", "")
