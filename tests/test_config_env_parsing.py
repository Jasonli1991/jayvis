"""數字型 env 解析的回歸測試。

複現並鎖住的 bug：.env 寫 `OWNER_CHAT_ID=`（key 存在、值為空字串）時，
舊寫法 `int(os.getenv("OWNER_CHAT_ID", "0"))` 會得到 `int('')` → ValueError，
讓 `import config` 在全新 .env 下直接崩潰（getenv 的預設只在 key 不存在時生效）。
修法：`_int_env` / `_float_env` 把「未設定 / 空字串 / 只有空白」一律視同未設定，退回預設。
"""
from config import _float_env, _int_env, _str_env


def test_int_env_unset_uses_default(monkeypatch):
    monkeypatch.delenv("JAYVIS_TEST_INT", raising=False)
    assert _int_env("JAYVIS_TEST_INT", 7) == 7


def test_int_env_empty_string_uses_default(monkeypatch):
    # .env 寫 KEY= 的情形：key 存在但值為空字串（原 bug 觸發點）
    monkeypatch.setenv("JAYVIS_TEST_INT", "")
    assert _int_env("JAYVIS_TEST_INT", 7) == 7


def test_int_env_whitespace_uses_default(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_INT", "   ")
    assert _int_env("JAYVIS_TEST_INT", 7) == 7


def test_int_env_real_value_parsed(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_INT", " 42 ")
    assert _int_env("JAYVIS_TEST_INT", 7) == 42


def test_float_env_empty_string_uses_default(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_FLOAT", "")
    assert _float_env("JAYVIS_TEST_FLOAT", 2.5) == 2.5


def test_float_env_whitespace_uses_default(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_FLOAT", "  ")
    assert _float_env("JAYVIS_TEST_FLOAT", 2.5) == 2.5


def test_float_env_real_value_parsed(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_FLOAT", "3.14")
    assert _float_env("JAYVIS_TEST_FLOAT", 2.5) == 3.14


def test_str_env_empty_uses_default(monkeypatch):
    # 面板存模型卡時欄位空白 → .env 寫 MODEL_GENERAL= → 不該變空，應退回預設
    monkeypatch.setenv("JAYVIS_TEST_STR", "")
    assert _str_env("JAYVIS_TEST_STR", "gemini-2.5-flash") == "gemini-2.5-flash"


def test_str_env_whitespace_uses_default(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_STR", "   ")
    assert _str_env("JAYVIS_TEST_STR", "fallback") == "fallback"


def test_str_env_real_value(monkeypatch):
    monkeypatch.setenv("JAYVIS_TEST_STR", " gpt-4o ")
    assert _str_env("JAYVIS_TEST_STR", "fallback") == "gpt-4o"
