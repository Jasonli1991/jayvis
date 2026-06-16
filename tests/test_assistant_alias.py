import assistant
import config


def test_addressee_line_with_alias(monkeypatch):
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {111: "Morgan"})
    line = assistant._addressee_line(111)
    assert "Morgan" in line and "對話對象" in line


def test_addressee_line_without_alias(monkeypatch):
    monkeypatch.setattr(config, "ALLOWLIST_ALIASES", {111: ""})
    assert assistant._addressee_line(111) == ""
    assert assistant._addressee_line(999) == ""
