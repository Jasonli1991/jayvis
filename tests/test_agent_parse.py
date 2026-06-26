from datetime import datetime

import agent


def test_parse_create_intent():
    txt = '好的 {"action":"create","title":"開會","start":"2026-06-15T15:00","end":"2026-06-15T16:00","notes":""}'
    i = agent.parse_intent(txt)
    assert i["action"] == "create" and i["title"] == "開會"


def test_parse_nested_update_intent():
    txt = '{"action":"update","match":{"title":"Max","date":"2026-06-15"},"changes":{"start":"2026-06-18T14:00"}}'
    i = agent.parse_intent(txt)
    assert i["action"] == "update"
    assert i["match"]["title"] == "Max"
    assert i["changes"]["start"] == "2026-06-18T14:00"


def test_non_action_returns_none():
    assert agent.parse_intent("你好，我是 Owner 的搭檔～") is None


def test_bad_json_returns_none():
    assert agent.parse_intent('{"action":"create", oops}') is None


def test_unknown_action_returns_none():
    assert agent.parse_intent('{"action":"launch_missiles"}') is None


def test_build_system_email_block():
    s = agent.build_system(datetime(2026, 6, 11), email_on=True, accounts=["a@x.com"])
    assert '"action":"send_email"' in s
    assert '"action":"list_email"' in s
    assert '"action":"read_email"' in s
    assert "a@x.com" in s


def test_build_system_excludes_code_intent():
    # 程式/PR/git/版本 不該被當成行事曆或郵件操作（避免「排『開PR』到行事曆」誤判）
    s = agent.build_system(datetime(2026, 6, 11))
    assert "程式委派" in s and "PR" in s


def test_build_system_email_off_by_default():
    s = agent.build_system(datetime(2026, 6, 11))     # email_on 預設 False
    assert "send_email" not in s
    assert '"action":"create"' in s                    # 行事曆預設仍在


def test_parse_send_email_intent():
    i = agent.parse_intent('{"action":"send_email","to":"a@b.com","subject":"S","body":"B"}')
    assert i["action"] == "send_email" and i["to"] == "a@b.com"


def test_parse_delete_email_ref():
    i = agent.parse_intent('{"action":"delete_email","ref":2}')
    assert i["action"] == "delete_email" and i["ref"] == 2


def test_build_system_has_delete_email():
    s = agent.build_system(datetime(2026, 6, 11), email_on=True)
    assert '"action":"delete_email"' in s


def test_build_system_body_dates_when_email_on():
    s = agent.build_system(datetime(2026, 6, 11), email_on=True)
    assert "寫成實際日期" in s            # 寄信內文也要換算日期
    s0 = agent.build_system(datetime(2026, 6, 11), email_on=False)
    assert "寫成實際日期" not in s0


def test_build_system_list_hint():
    s = agent.build_system(datetime(2026, 6, 11), email_on=True, last_list_n=10)
    assert "使用者剛列出 10 封" in s      # 消歧義：第幾封＝信
    s0 = agent.build_system(datetime(2026, 6, 11), email_on=True, last_list_n=0)
    assert "使用者剛列出" not in s0       # 沒列過信就不加提示


def test_build_system_injects_today():
    s = agent.build_system(datetime(2026, 6, 11))   # 週四
    assert "2026-06-11" in s
    assert "週四" in s
    assert '"action":"create"' in s
    assert "不要輸出 JSON" in s          # 非動作就正常回話
