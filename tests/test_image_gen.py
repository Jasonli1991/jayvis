import image_gen as ig


def test_split_marker_none_when_absent():
    assert ig.split_marker("純文字回答") == ("純文字回答", None)
    assert ig.split_marker("") == ("", None)


def test_split_marker_extracts_and_strips():
    clean, prompt = ig.split_marker("這是一隻貓\n\n[[圖：a cute cat on the moon]]")
    assert clean == "這是一隻貓"
    assert prompt == "a cute cat on the moon"


def test_split_marker_halfwidth_colon_and_multiple():
    clean, prompt = ig.split_marker("答案[[圖:first]]中間[[圖：second]]尾")
    assert prompt == "first"                 # 取第一個
    assert "[[圖" not in clean               # 全部標記移除


def test_generate_returns_bytes_on_success(monkeypatch):
    class _R:
        def read(self): return b"\x89PNG" + b"x" * 500
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda url, timeout=0: _R())
    assert ig.generate("a cat") == b"\x89PNG" + b"x" * 500


def test_generate_sends_user_agent(monkeypatch):
    # Pollinations 會擋掉沒有 User-Agent 的請求 → 必須帶 UA
    cap = {}
    class _R:
        def read(self): return b"\xff\xd8" + b"x" * 500
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake(req, timeout=0):
        cap["ua"] = req.get_header("User-agent")
        return _R()
    monkeypatch.setattr(ig.urllib.request, "urlopen", fake)
    assert ig.generate("a cat")
    assert cap["ua"] and "Mozilla" in cap["ua"]


def test_generate_none_on_failure(monkeypatch):
    def boom(url, timeout=0):
        raise OSError("net down")
    monkeypatch.setattr(ig.urllib.request, "urlopen", boom)
    assert ig.generate("a cat") is None


def test_generate_none_on_empty_prompt(monkeypatch):
    called = []
    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda *a, **k: called.append(1))
    assert ig.generate("   ") is None
    assert called == []                      # 空 prompt 不打網路
