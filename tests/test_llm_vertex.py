import os

import pytest

import llm
import config


# 這是「真打 LLM API」的整合測試：會看供應商臉色（免費方案 503 高峰、配額等），
# 不該進預設套件造成偽紅。需明確設 RUN_LIVE_LLM=1 才跑。
@pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="set RUN_LIVE_LLM=1 to run live LLM call")
def test_generate_flash_returns_text():
    out = llm.generate(
        model=config.MODEL_GENERAL,
        system="你只能回覆兩個字：收到",
        messages=[{"role": "user", "content": "請回覆"}],
        max_output_tokens=512,
    )
    assert isinstance(out, str) and out.strip() != ""
