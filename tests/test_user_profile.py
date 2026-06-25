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


def test_maybe_update_triggers_by_persistent_turns(monkeypatch):
    # 依持久化的對話則數觸發（非記憶體計數器）：累積到門檻才背景抽取
    import memory
    user_profile.reset()
    spawned = {"n": 0}
    monkeypatch.setattr(user_profile, "_spawn", lambda pid: spawned.__setitem__("n", spawned["n"] + 1))
    for i in range(user_profile.PROFILE_EVERY_N * 2 - 1):          # 差一則
        memory.append("6803", "user" if i % 2 == 0 else "assistant", f"訊息{i}")
    user_profile.maybe_update("6803")
    assert spawned["n"] == 0
    memory.append("6803", "assistant", "再一則")
    user_profile.maybe_update("6803")
    assert spawned["n"] == 1                                       # 到門檻 → 觸發


def test_maybe_update_survives_restart(monkeypatch):
    # 關鍵：模擬 bot 重啟（reset 清掉所有記憶體狀態）後，仍能依持久化對話數觸發
    # —— 舊版記憶體計數器會歸零 → 永遠不更新，正是「長期認識一直空白」的根因
    import memory
    user_profile.reset()
    spawned = {"n": 0}
    monkeypatch.setattr(user_profile, "_spawn", lambda pid: spawned.__setitem__("n", spawned["n"] + 1))
    for i in range(user_profile.PROFILE_EVERY_N * 2):
        memory.append("6803", "user", f"訊息{i}")
    user_profile.reset()                                          # ← 模擬重啟
    user_profile.maybe_update("6803")
    assert spawned["n"] == 1                                       # 仍觸發（不靠記憶體計數器）


def test_maybe_update_counts_only_turns_since_profile(monkeypatch):
    # 有畫像後，只計 updated_at 之後的新對話；少量新對話不該重複觸發
    import memory
    user_profile.reset()
    spawned = {"n": 0}
    monkeypatch.setattr(user_profile, "_spawn", lambda pid: spawned.__setitem__("n", spawned["n"] + 1))
    user_profile._write("6803", "- 舊畫像")                        # 設了 updated_at
    for i in range(user_profile.PROFILE_EVERY_N):                  # < 門檻(*2)
        memory.append("6803", "user", f"新{i}")
    user_profile.maybe_update("6803")
    assert spawned["n"] == 0


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


