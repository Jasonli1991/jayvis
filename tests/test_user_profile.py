import config
import user_profile


def test_write_get_clear():
    user_profile.reset()
    user_profile._write("6803", "- 偏好繁中\n- 在做 JAYVIS")
    assert "JAYVIS" in user_profile.get("6803")
    user_profile.clear("6803")
    assert user_profile.get("6803") == ""


def test_get_empty_is_blank():
    user_profile.reset()
    assert user_profile.get("nope") == ""


def test_prompt_block_empty_and_filled(monkeypatch):
    user_profile.reset()
    monkeypatch.setattr(config, "OWNER_NAME", "Owner")
    assert user_profile.prompt_block("6803") == ""
    user_profile._write("6803", "- 偏好繁中")
    blk = user_profile.prompt_block("6803")
    assert "長期認識" in blk and "非權威" in blk and "Owner" in blk and "偏好繁中" in blk


def test_note_turn_threshold():
    user_profile.reset()
    for _ in range(5):
        assert user_profile.note_turn("6803") is False
    assert user_profile.note_turn("6803") is True       # 第 6 次觸發
    assert user_profile.note_turn("6803") is False       # 歸零後重數


def test_note_turn_per_person():
    user_profile.reset()
    for _ in range(5):
        user_profile.note_turn("A")
    assert user_profile.note_turn("B") is False           # B 獨立計數


def test_update_now_writes_merged_profile(monkeypatch):
    user_profile.reset()
    monkeypatch.setattr(user_profile.memory, "recent",
                        lambda p, k=None: [{"role": "user", "content": "我偏好繁中、直接"},
                                           {"role": "assistant", "content": "好"}])
    seen = {}
    monkeypatch.setattr(user_profile, "generate",
                        lambda **kw: seen.update(system=kw["system"]) or "- 偏好繁中、直接")
    user_profile.update_now("6803")
    assert "偏好繁中" in user_profile.get("6803")
    assert "耐久" in seen["system"]                       # 抽取 prompt 強調耐久資訊


def test_update_now_no_turns_no_write(monkeypatch):
    user_profile.reset()
    monkeypatch.setattr(user_profile.memory, "recent", lambda p, k=None: [])
    called = {"n": 0}
    monkeypatch.setattr(user_profile, "generate", lambda **kw: called.__setitem__("n", 1) or "x")
    user_profile.update_now("6803")
    assert called["n"] == 0 and user_profile.get("6803") == ""


def test_update_now_llm_error_keeps_old(monkeypatch):
    user_profile.reset()
    user_profile._write("6803", "- 舊畫像")
    monkeypatch.setattr(user_profile.memory, "recent", lambda p, k=None: [{"role": "user", "content": "x"}])

    def boom(**kw):
        raise RuntimeError("quota")

    monkeypatch.setattr(user_profile, "generate", boom)
    user_profile.update_now("6803")
    assert user_profile.get("6803") == "- 舊畫像"          # 失敗保留舊


def test_maybe_update_spawns_only_at_threshold(monkeypatch):
    user_profile.reset()
    spawned = {"n": 0}
    monkeypatch.setattr(user_profile, "_spawn", lambda pid: spawned.__setitem__("n", spawned["n"] + 1))
    for _ in range(5):
        user_profile.maybe_update("6803")
    assert spawned["n"] == 0
    user_profile.maybe_update("6803")                      # 第 6 次
    assert spawned["n"] == 1
