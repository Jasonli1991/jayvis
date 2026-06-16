import config
from router import choose_model


def test_code_keyword_routes_to_code_model():
    assert choose_model("這個 function 為什麼會報錯 error") == config.MODEL_CODE
    assert choose_model("projx 的部署流程") == config.MODEL_CODE


def test_any_git_source_routes_to_code_model():
    # 檢索到任何 git 來源 → 走 pro（即使問句沒程式關鍵字）
    assert choose_model("這個東西", source_types=["git", "obsidian", "obsidian", "obsidian"]) == config.MODEL_CODE
    assert choose_model("這個怎麼處理", source_types=["git", "git", "obsidian"]) == config.MODEL_CODE


def test_general_question_routes_to_general_model():
    assert choose_model("這個客戶比較喜歡什麼風格") == config.MODEL_GENERAL
    assert choose_model("專案進度到哪", source_types=["obsidian", "chat"]) == config.MODEL_GENERAL


def test_empty_inputs_default_general():
    assert choose_model("") == config.MODEL_GENERAL
