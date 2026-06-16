import mail_tool as mt


def test_esc():
    assert mt._esc('a"b\\c') == 'a\\"b\\\\c'


def test_script_send_basic():
    s = mt._script_send("a@b.com", "嗨", "內文", "")
    assert 'subject:"嗨"' in s and 'content:"內文"' in s
    assert 'address:"a@b.com"' in s
    assert "set sender" not in s            # 沒給帳號就不設 sender
    assert "send newMsg" in s


def test_script_send_with_account():
    s = mt._script_send("a@b.com", "S", "B", "me@x.com")
    assert 'set sender of newMsg to "me@x.com"' in s


def test_script_list_inbox_unread():
    s = mt._script_list_inbox("unread", 10)
    assert "read status of m" in s          # 未讀過濾
    assert "id of m" in s and "sender of m" in s and "subject of m" in s
    assert "1 thru" in s                    # slice 限縮


def test_script_list_inbox_recent():
    s = mt._script_list_inbox("recent", 5)
    assert "read status" not in s           # recent 不過濾
    assert "≥ 5" in s


def test_parse_msgs():
    raw = ("101" + mt.SEP + "Sam <s@x>" + mt.SEP + "報告" + mt.SEP + "2026-06-11"
           + "\n" + "102" + mt.SEP + "Jordan <j@x>" + mt.SEP + "午餐" + mt.SEP + "2026-06-11")
    out = mt._parse_msgs(raw)
    assert out[0] == {"id": "101", "from": "Sam <s@x>", "subject": "報告", "date": "2026-06-11"}
    assert mt._parse_msgs("") == []


def test_script_read_truncates():
    s = mt._script_read("101")
    assert "whose id is 101" in s
    assert f"text 1 thru {mt.MAX_BODY}" in s
    assert "content of m" in s


def test_script_list_accounts():
    s = mt._script_list_accounts()
    assert "email addresses of a" in s


def test_script_delete():
    s = mt._script_delete("101")
    assert "whose id is 101" in s
    assert "delete (" in s
