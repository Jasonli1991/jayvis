"""低階瀏覽器操作：Playwright connect_over_cdp 接 owner 已登入的 Chrome。同步 API，跑在 worker thread。"""
import glob
import os

import config
import browse_allowlist
import browse_launch

_INTERACTABLE = "a,button,input,textarea,select,[role=button],[role=link]"

_pw = None
_browser = None
_page = None


class BrowseUnavailable(RuntimeError):
    """Chrome 沒開遠端偵錯 / CDP 連不上。"""


class NotAllowed(RuntimeError):
    """網域不在白名單。"""


def _open_cdp():
    """連到既有 Chrome，回 (pw, browser, page)。被測試 monkeypatch。"""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(config.BROWSE_CDP_URL)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, browser, page


def connect() -> None:
    global _pw, _browser, _page
    if _page is not None:
        return
    try:
        _pw, _browser, _page = _open_cdp()
        return
    except Exception:
        pass
    # 自癒：專用 Chrome 可能被關了 → 嘗試啟動後重試一次
    try:
        browse_launch.launch()
        _pw, _browser, _page = _open_cdp()
    except Exception as e:           # 仍連不上 → 統一成 BrowseUnavailable
        raise BrowseUnavailable(str(e))


def reset() -> None:
    global _pw, _browser, _page
    _pw = _browser = _page = None


def _require_page():
    if _page is None:
        connect()
    return _page


def current_url() -> str:
    return _require_page().url


def _guard_current() -> None:
    if not browse_allowlist.is_allowed(current_url()):
        raise NotAllowed(current_url())


def goto(url: str) -> None:
    if not browse_allowlist.is_allowed(url):
        raise NotAllowed(url)
    _require_page().goto(url, timeout=config.BROWSE_NAV_TIMEOUT_S * 1000)


def snapshot() -> list:
    _guard_current()
    els = _require_page().query_selector_all(_INTERACTABLE)
    out = []
    for i, el in enumerate(els):
        try:
            name = (el.inner_text() or el.get_attribute("aria-label")
                    or el.get_attribute("value") or "").strip()
            tag = el.evaluate("e => e.tagName.toLowerCase()")
        except Exception:
            name, tag = "", ""
        out.append({"ref": i, "tag": tag, "name": name[:80]})
    return out


def extract_text() -> str:
    _guard_current()
    return (_require_page().inner_text("body") or "")[:6000]


def screenshot() -> bytes:
    _guard_current()
    return _require_page().screenshot(full_page=False, animations="disabled",
                                      timeout=config.BROWSE_NAV_TIMEOUT_S * 1000)


def _nth(ref: int):
    els = _require_page().query_selector_all(_INTERACTABLE)
    if ref is None or ref < 0 or ref >= len(els):
        raise ValueError(f"ref {ref} 不存在")
    return els[ref]


def click(ref: int) -> None:
    _guard_current()
    _nth(ref).click(timeout=config.BROWSE_NAV_TIMEOUT_S * 1000)


def type_text(ref: int, text: str) -> None:
    _guard_current()
    _nth(ref).fill(text or "")


def sweep_tmp() -> None:
    d = config.BROWSE_TMP_DIR
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, "*")):
            try:
                os.remove(f)
            except OSError:
                pass
