from safety import sanitize


def test_blocks_private_key():
    s = sanitize("foo\n-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")
    assert s.blocked is True
    assert "private_key" in s.reasons


def test_blocks_api_key_token():
    s = sanitize("here is the key sk-ant-api03-AAAA1111BBBB2222CCCC3333DDDD4444")
    assert s.blocked is True


def test_masks_email_and_phone_but_not_blocked():
    s = sanitize("聯絡 you@example.com 電話 0900000000")
    assert s.blocked is False
    assert "you@example.com" not in s.text
    assert "0900000000" not in s.text
    assert "[email]" in s.text and "[phone]" in s.text


def test_clean_text_passes_through():
    s = sanitize("projy 改用 pgvector 做檢索")
    assert s.blocked is False
    assert s.text == "projy 改用 pgvector 做檢索"
