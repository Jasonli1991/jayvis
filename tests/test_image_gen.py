import image_gen as ig


def test_split_caption():
    assert ig._split_caption("a rocket | 硬著陸") == ("a rocket", "硬著陸")
    assert ig._split_caption("just a cat") == ("just a cat", None)
    assert ig._split_caption("a|") == ("a", None)       # 空字幕視為無


def test_craft_prompt_returns_llm_line(monkeypatch):
    monkeypatch.setattr(ig, "_llm_generate", lambda **k: '  a cat on the moon, digital art \n')
    assert ig.craft_prompt("畫一隻在月球的貓") == "a cat on the moon, digital art"


def test_craft_prompt_empty_on_llm_failure(monkeypatch):
    def boom(**k):
        raise RuntimeError("quota")
    monkeypatch.setattr(ig, "_llm_generate", boom)
    assert ig.craft_prompt("畫一隻貓") == ""


def test_overlay_caption_returns_valid_image():
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (400, 400), "gray").save(buf, "JPEG")
    out = ig._overlay_caption(buf.getvalue(), "測試字幕 hello world 換行很長很長很長很長很長很長很長很長")
    assert isinstance(out, bytes) and len(out) > 100
    Image.open(BytesIO(out)).verify()                   # 可被 PIL 開啟＝有效圖


def _gray_jpeg():
    from io import BytesIO
    from PIL import Image
    b = BytesIO()
    Image.new("RGB", (300, 300), "gray").save(b, "JPEG")
    return b.getvalue()


def test_generate_returns_bytes_on_success(monkeypatch):
    class _R:
        def read(self): return _gray_jpeg()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda req, timeout=0: _R())
    assert ig.generate("a cat") == _gray_jpeg()


def test_generate_overlays_caption_when_present(monkeypatch):
    class _R:
        def read(self): return _gray_jpeg()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda req, timeout=0: _R())
    cap = {}
    monkeypatch.setattr(ig, "_overlay_caption", lambda b, c: cap.__setitem__("c", c) or b"OVERLAID")
    assert ig.generate("a rocket | 暴跌啦") == b"OVERLAID"
    assert cap["c"] == "暴跌啦"


def test_generate_sends_user_agent(monkeypatch):
    cap = {}
    class _R:
        def read(self): return _gray_jpeg()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def fake(req, timeout=0):
        cap["ua"] = req.get_header("User-agent")
        return _R()
    monkeypatch.setattr(ig.urllib.request, "urlopen", fake)
    assert ig.generate("a cat")
    assert cap["ua"] and "Mozilla" in cap["ua"]


def test_generate_none_on_failure(monkeypatch):
    def boom(req, timeout=0):
        raise OSError("net down")
    monkeypatch.setattr(ig.urllib.request, "urlopen", boom)
    assert ig.generate("a cat") is None


def test_generate_none_on_empty_prompt(monkeypatch):
    called = []
    monkeypatch.setattr(ig.urllib.request, "urlopen", lambda *a, **k: called.append(1))
    assert ig.generate("   ") is None
    assert called == []                      # 空 prompt 不打網路
