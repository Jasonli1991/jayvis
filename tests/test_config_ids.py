from config import _parse_ids


def test_parse_ids_basic():
    assert _parse_ids("123, 456,789") == {123, 456, 789}


def test_parse_ids_empty():
    assert _parse_ids("") == set()
    assert _parse_ids("   ") == set()


def test_parse_ids_ignores_blanks():
    assert _parse_ids("1,,2, ,3") == {1, 2, 3}
