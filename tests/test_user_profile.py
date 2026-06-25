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
    systems = []                                          # update_now 現在會呼叫 generate 兩次（合併＋頭像特徵）
    monkeypatch.setattr(user_profile, "generate",
                        lambda **kw: systems.append(kw["system"]) or "- 偏好繁中、直接")
    user_profile.update_now("6803")
    assert "偏好繁中" in user_profile.get("6803")
    assert any("耐久" in s for s in systems)              # 抽取 prompt 強調耐久資訊


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


# --- 後台塗鴉頭像：臉部特徵 spec（依觀察抽、可清除） ---

def test_norm_portrait_defaults_invalid_values():
    spec = user_profile._norm_portrait({"mood": "tired", "eyes": "BOGUS",
                                        "eyeBags": "1", "accessory": "coffee"})
    assert spec["mood"] == "tired"                                  # 合法 → 保留
    assert spec["eyes"] == user_profile._PORTRAIT_DEFAULT["eyes"]   # 非法 → 預設
    assert spec["eyeBags"] == 1                                     # "1" → 1
    assert spec["accessory"] == "coffee"
    assert set(spec.keys()) == set(user_profile.PORTRAIT_VOCAB.keys())   # 一律補滿所有欄位


def test_norm_portrait_non_dict_is_none():
    assert user_profile._norm_portrait("nope") is None
    assert user_profile._norm_portrait(None) is None


def test_parse_portrait_extracts_json_amid_noise():
    out = '好的：```json\n{"mood":"stressed","brows":"furrowed","eyeBags":1}\n```'
    spec = user_profile._parse_portrait(out)
    assert spec["mood"] == "stressed" and spec["brows"] == "furrowed" and spec["eyeBags"] == 1


def test_parse_portrait_no_json_is_none():
    assert user_profile._parse_portrait("沒有 JSON 啦") is None
    assert user_profile._parse_portrait("") is None


def test_update_now_writes_portrait_from_observation(monkeypatch):
    # 畫像更新後，第二次模型呼叫抽臉部特徵並存進 portrait 欄
    user_profile.reset()
    monkeypatch.setattr(user_profile.memory, "recent",
                        lambda p, k=None: [{"role": "user", "content": "又熬夜寫扣、靠咖啡撐"}])

    def fake_gen(**kw):
        if "耐久" in kw["system"]:
            return "- 常熬夜\n- 咖啡成癮"
        return '{"mood":"tired","eyes":"tired","eyeBags":1,"accessory":"coffee"}'

    monkeypatch.setattr(user_profile, "generate", fake_gen)
    user_profile.update_now("6803")
    spec = user_profile.get_portrait("6803")
    assert spec is not None
    assert spec["eyeBags"] == 1 and spec["accessory"] == "coffee" and spec["eyes"] == "tired"


def test_get_portrait_none_when_unset(monkeypatch):
    user_profile.reset()
    user_profile._write("6803", "- 有畫像但沒頭像")
    assert user_profile.get_portrait("6803") is None       # 只寫 profile、沒 portrait
    assert user_profile.get_portrait("nobody") is None


def test_update_now_bad_portrait_json_leaves_portrait_unset(monkeypatch):
    user_profile.reset()
    monkeypatch.setattr(user_profile.memory, "recent",
                        lambda p, k=None: [{"role": "user", "content": "x"}])
    monkeypatch.setattr(user_profile, "generate",
                        lambda **kw: "- 新畫像" if "耐久" in kw["system"] else "亂回沒有 JSON")
    user_profile.update_now("6803")
    assert "新畫像" in user_profile.get("6803")
    assert user_profile.get_portrait("6803") is None       # 特徵格式錯 → 不寫頭像（不炸）


def test_clear_also_drops_portrait():
    user_profile.reset()
    user_profile._write("6803", "- p")
    user_profile._write_portrait("6803", {"mood": "cheerful"})
    assert user_profile.get_portrait("6803") is not None
    user_profile.clear("6803")
    assert user_profile.get_portrait("6803") is None


def test_norm_portrait_includes_gender_default():
    assert user_profile._norm_portrait({})["gender"] == "neutral"            # 沒指定 → 不亂猜性別
    assert user_profile._norm_portrait({"gender": "femme"})["gender"] == "femme"
    assert user_profile._norm_portrait({"gender": "??"})["gender"] == "neutral"   # 非法 → 預設


def test_extract_portrait_passes_owner_name_for_gender(monkeypatch):
    seen = {}

    def cap(**kw):
        seen["system"] = kw["system"]
        return '{"gender":"femme","mood":"calm"}'

    monkeypatch.setattr(user_profile, "generate", cap)
    spec = user_profile._extract_portrait("- 喜歡園藝", owner_name="Alice")
    assert "Alice" in seen["system"] and "性別" in seen["system"]    # 名字進 prompt、要求判性別
    assert spec["gender"] == "femme"


