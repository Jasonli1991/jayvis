import importlib
import io
import json as _json
import os

import config
import websearch


def test_search_config_parses_env(monkeypatch):
    # 顯式給值（load_dotenv override=False 不會蓋過 env）→ 不依賴真實 .env 是否已啟用搜尋
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    importlib.reload(config)
    assert config.SEARCH_ENABLED is False and config.TAVILY_API_KEY == ""
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    importlib.reload(config)
    assert config.SEARCH_ENABLED is True


def teardown_module(module):
    # 還原 config 成真實 .env，避免 reload 後的值污染其他測試
    for k in ("SEARCH_ENABLED", "TAVILY_API_KEY"):
        os.environ.pop(k, None)
    importlib.reload(config)


def test_looks_like_current_events():
    assert websearch.looks_like_current_events("今天台股怎樣")
    assert websearch.looks_like_current_events("最新的美元匯率")
    assert websearch.looks_like_current_events("現在天氣如何")
    assert not websearch.looks_like_current_events("幫我訂機票")
    assert not websearch.looks_like_current_events("謝謝你")


def test_search_returns_clean_results(monkeypatch):
    monkeypatch.setattr(config, "TAVILY_API_KEY", "k")
    payload = _json.dumps({"results": [
        {"title": "台股收紅", "url": "http://a", "content": "加權指數上漲", "extra": "略"},
        {"title": "美元走弱", "url": "http://b", "content": "匯率下跌"},
    ]}).encode()
    monkeypatch.setattr(websearch.urllib.request, "urlopen",
                        lambda req, timeout=0: io.BytesIO(payload))
    out = websearch.search("今天台股", n=5)
    assert out == [
        {"title": "台股收紅", "url": "http://a", "content": "加權指數上漲"},
        {"title": "美元走弱", "url": "http://b", "content": "匯率下跌"},
    ]


def test_search_empty_success_returns_empty_list(monkeypatch):
    # API 正常回應、但查無結果 → []（成功但空），與「失敗」區分
    monkeypatch.setattr(config, "TAVILY_API_KEY", "k")
    monkeypatch.setattr(websearch.urllib.request, "urlopen",
                        lambda req, timeout=0: io.BytesIO(_json.dumps({"results": []}).encode()))
    assert websearch.search("今天台股") == []


def test_search_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(config, "TAVILY_API_KEY", "")
    assert websearch.search("今天台股") is None          # 不能搜＝失敗（None），非查無（[]）


def test_search_on_error_returns_none(monkeypatch):
    monkeypatch.setattr(config, "TAVILY_API_KEY", "k")

    def boom(req, timeout=0):
        raise OSError("timeout")

    monkeypatch.setattr(websearch.urllib.request, "urlopen", boom)
    assert websearch.search("今天台股") is None


def test_search_quota_returns_none(monkeypatch):
    # Tavily 額度用完：HTTP 429 → urlopen 丟 HTTPError → None（失敗）
    import urllib.error
    monkeypatch.setattr(config, "TAVILY_API_KEY", "k")

    def quota(req, timeout=0):
        raise urllib.error.HTTPError("u", 429, "usage limit exceeded", {}, None)

    monkeypatch.setattr(websearch.urllib.request, "urlopen", quota)
    assert websearch.search("今天台股") is None
