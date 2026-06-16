import config


def test_llm_config_defaults():
    # GCP_PROJECT 為使用者自填（.env），公開版預設留空；只驗屬性存在、型別為字串
    assert isinstance(config.GCP_PROJECT, str)
    assert config.GCP_LOCATION
    # 模型名為使用者可設定（.env 覆寫），只驗有值，不寫死特定模型
    assert config.MODEL_GENERAL
    assert config.MODEL_CODE
