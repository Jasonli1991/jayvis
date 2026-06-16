import obsidian_folders


def test_label_for_longest_prefix(monkeypatch, tmp_path):
    monkeypatch.setattr(obsidian_folders, "_PATH", tmp_path / "none.json")   # 用內建預設
    assert obsidian_folders.label_for("02_Outputs/Q&A/foo.md") == "問答紀錄"
    assert obsidian_folders.label_for("04_Archive/Projects/x.md") == "封存"
    assert obsidian_folders.label_for("01_Wiki/a/b.md") == "知識條目"
    assert obsidian_folders.label_for("random/x.md") == "筆記"      # 無匹配


def test_prompt_legend(monkeypatch, tmp_path):
    monkeypatch.setattr(obsidian_folders, "_PATH", tmp_path / "none.json")
    s = obsidian_folders.prompt_legend()
    assert "資料夾語意" in s and "問答紀錄" in s and "封存" in s


def test_load_custom_json(monkeypatch, tmp_path):
    import json
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"X": {"label": "自訂", "note": "n"}}), encoding="utf-8")
    monkeypatch.setattr(obsidian_folders, "_PATH", p)
    assert obsidian_folders.label_for("X/a.md") == "自訂"


def test_load_broken_json_falls_back(monkeypatch, tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(obsidian_folders, "_PATH", p)
    assert obsidian_folders.label_for("01_Wiki/a.md") == "知識條目"   # 壞檔 → 預設
