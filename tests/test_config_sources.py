import config


def test_repos_default_when_unset():
    # 未設定 GITHUB_REPOS 時回傳預設清單（公開版預設為空＝不追蹤 GitHub）
    assert config._parse_repos(None) == config._GITHUB_DEFAULT


def test_repos_empty_string_disables():
    assert config._parse_repos("") == []
    assert config._parse_repos("  ") == []


def test_repos_parse_comma_and_newline():
    assert config._parse_repos("a/b, c/d") == ["a/b", "c/d"]
    assert config._parse_repos("a/b\nc/d\n") == ["a/b", "c/d"]
