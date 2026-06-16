import calendar_tool as ct


def test_esc_quotes_and_backslash():
    assert ct._esc('a"b\\c') == 'a\\"b\\\\c'


def test_cal_clause():
    assert ct._cal_clause("Home") == 'calendar "Home"'
    assert ct._cal_clause("") == "calendar 1"          # 空＝第一本


def test_script_create_has_components_and_summary():
    s = ct._script_create("Home", "與 Max 開會", "2026-06-15T15:00", "2026-06-15T16:00", "")
    assert 'calendar "Home"' in s
    assert "set year of d1 to 2026" in s
    assert "set month of d1 to 6" in s
    assert "set day of d1 to 15" in s
    assert "set hours of d1 to 15" in s
    assert "set hours of d2 to 16" in s
    assert 'summary:"與 Max 開會"' in s
    assert "return uid of newEvent" in s


def test_script_list_window_and_iso_handler():
    s = ct._script_list("Home", "2026-06-15T00:00", "2026-06-16T00:00")
    assert "whose start date" in s
    assert "set year of s to 2026" in s
    assert "on isoOf(" in s                  # 自帶 ISO 格式化 handler（避開 locale）


def test_parse_events():
    raw = ("ABC123" + ct.SEP + "與 Max 開會" + ct.SEP + "2026-06-15T15:00" + ct.SEP + "2026-06-15T16:00"
           + "\n" + "DEF456" + ct.SEP + "午餐" + ct.SEP + "2026-06-15T12:00" + ct.SEP + "2026-06-15T13:00")
    evs = ct._parse_events(raw)
    assert len(evs) == 2
    assert evs[0] == {"uid": "ABC123", "title": "與 Max 開會",
                      "start": "2026-06-15T15:00", "end": "2026-06-15T16:00"}
    assert ct._parse_events("") == []


def test_script_update_only_changed_fields():
    s = ct._script_update("Home", "ABC123", {"start": "2026-06-18T14:00", "end": "2026-06-18T15:00"})
    assert 'whose uid is "ABC123"' in s
    assert "set start date of ev to d1" in s
    assert "set end date of ev to d2" in s
    assert "set summary of ev" not in s         # title 沒給就不動

    s2 = ct._script_update("Home", "ABC123", {"title": "改名"})
    assert 'set summary of ev to "改名"' in s2
    assert "set start date" not in s2


def test_script_delete_by_uid():
    s = ct._script_delete("Home", "ABC123")
    assert 'delete (every event whose uid is "ABC123")' in s
    assert 'calendar "Home"' in s
