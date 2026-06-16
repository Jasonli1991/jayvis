import os
import sys

import pytest

import mail_tool as mt


def test_send_mail(monkeypatch):
    seen = {}

    def _fake(script):
        seen["script"] = script
        return ""

    monkeypatch.setattr(mt, "_run", _fake)
    assert mt.send_mail("a@b.com", "嗨", "內文", account="me@x.com") == {"sent": True}
    assert 'address:"a@b.com"' in seen["script"]
    assert 'set sender of newMsg to "me@x.com"' in seen["script"]


def test_list_inbox_parses(monkeypatch):
    raw = "101" + mt.SEP + "Sam" + mt.SEP + "報告" + mt.SEP + "2026-06-11"
    monkeypatch.setattr(mt, "_run", lambda s: raw)
    out = mt.list_inbox("unread", 10)
    assert out == [{"id": "101", "from": "Sam", "subject": "報告", "date": "2026-06-11"}]


def test_read_message(monkeypatch):
    monkeypatch.setattr(mt, "_run", lambda s: "Sam" + mt.SEP + "報告" + mt.SEP + "內文很長…")
    m = mt.read_message("101")
    assert m == {"from": "Sam", "subject": "報告", "body": "內文很長…"}


def test_list_accounts_dedupes(monkeypatch):
    monkeypatch.setattr(mt, "_run", lambda s: "a@x.com\nb@y.com\na@x.com\n")
    assert mt.list_accounts() == ["a@x.com", "b@y.com"]


def test_delete_message(monkeypatch):
    seen = {}
    monkeypatch.setattr(mt, "_run", lambda s: seen.setdefault("s", s) or "")
    assert mt.delete_message("101") == {"deleted": True}
    assert "whose id is 101" in seen["s"]


@pytest.mark.skipif(not os.getenv("RUN_MAIL") or sys.platform != "darwin",
                    reason="set RUN_MAIL=1 on macOS to hit real Mail")
def test_real_list_accounts_and_inbox():
    assert isinstance(mt.list_accounts(), list)
    assert isinstance(mt.list_inbox("unread", 3), list)
