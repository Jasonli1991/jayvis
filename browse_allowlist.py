"""瀏覽網域白名單：~/.n/browse_allowlist.json。空白名單＝全拒（fail-closed）。"""
import json
from pathlib import Path
from urllib.parse import urlparse

_PATH = Path.home() / ".n" / "browse_allowlist.json"


def load() -> list:
    if not _PATH.exists():
        return []
    try:
        return list(json.loads(_PATH.read_text(encoding="utf-8")).get("domains", []))
    except (ValueError, OSError):
        return []


def save(domains: list) -> None:
    norm, seen = [], set()
    for d in domains:
        d = (d or "").strip().lower()
        if d and d not in seen:
            seen.add(d)
            norm.append(d)
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps({"domains": norm}, ensure_ascii=False, indent=2),
                     encoding="utf-8")


def is_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for d in load():
        if host == d or host.endswith("." + d):
            return True
    return False


def add(domain: str) -> None:
    save(load() + [domain])


def remove(domain: str) -> None:
    d = (domain or "").strip().lower()
    save([x for x in load() if x != d])
