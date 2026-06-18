import analysis


def test_clean_html_strips_fences():
    assert analysis._clean_html("```html\n<html></html>\n```") == "<html></html>"
    assert analysis._clean_html("```\n<html></html>\n```") == "<html></html>"
    assert analysis._clean_html("<html></html>") == "<html></html>"


def test_looks_like_html():
    assert analysis._looks_like_html("<!DOCTYPE html><html>") is True
    assert analysis._looks_like_html("<canvas id=x></canvas>") is True
    assert analysis._looks_like_html("just plain text") is False


def test_inject_chartjs_after_head(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<html><head><title>x</title></head><body></body></html>")
    assert "<head><script>/*CJS*/</script>" in out


def test_inject_chartjs_no_head(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<html><body></body></html>")
    assert out.startswith("<html><script>/*CJS*/</script>")


def test_inject_chartjs_no_html_tag(monkeypatch):
    monkeypatch.setattr(analysis, "_CHARTJS", "/*CJS*/")
    out = analysis._inject_chartjs("<canvas></canvas>")
    assert out.startswith("<script>/*CJS*/</script>")
