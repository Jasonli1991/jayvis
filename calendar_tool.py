"""macOS Calendar 操作（透過 osascript）。純函式產生 AppleScript、執行、解析。
日期用逐欄設定（locale-safe），不靠 `date "字串"`。"""
import subprocess
import sys
from datetime import datetime

import config

SEP = "\x1f"   # 欄位分隔（unit separator，事件文字不會用到）


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _cal_clause(calendar: str) -> str:
    return f'calendar "{_esc(calendar)}"' if calendar else "calendar 1"


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)               # "YYYY-MM-DDTHH:MM"


def _set_date(var: str, dt: datetime) -> str:
    return "\n".join([
        f"set {var} to (current date)",
        f"set year of {var} to {dt.year}",
        f"set month of {var} to {dt.month}",
        f"set day of {var} to {dt.day}",
        f"set hours of {var} to {dt.hour}",
        f"set minutes of {var} to {dt.minute}",
        f"set seconds of {var} to 0",
    ])


def _script_create(calendar, title, start, end, notes="", all_day=False) -> str:
    allday = ", allday event:true" if all_day else ""
    return f'''tell application "Calendar"
  tell {_cal_clause(calendar)}
{_set_date("d1", _dt(start))}
{_set_date("d2", _dt(end))}
    set newEvent to make new event with properties {{summary:"{_esc(title)}", start date:d1, end date:d2, description:"{_esc(notes)}"{allday}}}
    return uid of newEvent
  end tell
end tell'''


_ISO_HANDLER = '''
on pad(n)
  set n to n as integer
  if n < 10 then return "0" & n
  return n as string
end pad
on isoOf(dt)
  return (year of dt as string) & "-" & my pad(month of dt as integer) & "-" & my pad(day of dt) & "T" & my pad(hours of dt) & ":" & my pad(minutes of dt)
end isoOf
'''


def _script_list(calendar, start, end) -> str:
    return f'''{_ISO_HANDLER}
tell application "Calendar"
  tell {_cal_clause(calendar)}
{_set_date("s", _dt(start))}
{_set_date("e", _dt(end))}
    set evs to (every event whose start date ≥ s and start date < e)
    set out to ""
    repeat with ev in evs
      set out to out & (uid of ev) & "{SEP}" & (summary of ev) & "{SEP}" & my isoOf(start date of ev) & "{SEP}" & my isoOf(end date of ev) & linefeed
    end repeat
    return out
  end tell
end tell'''


def _parse_events(raw: str) -> list:
    events = []
    for line in (raw or "").splitlines():
        parts = line.split(SEP)
        if len(parts) == 4:
            events.append({"uid": parts[0], "title": parts[1],
                           "start": parts[2], "end": parts[3]})
    return events


def _script_update(calendar, uid, changes: dict) -> str:
    sets, pre = [], []
    if "start" in changes:
        pre.append(_set_date("d1", _dt(changes["start"])))
        sets.append("      set start date of ev to d1")
    if "end" in changes:
        pre.append(_set_date("d2", _dt(changes["end"])))
        sets.append("      set end date of ev to d2")
    if "title" in changes:
        sets.append(f'      set summary of ev to "{_esc(changes["title"])}"')
    if "notes" in changes:
        sets.append(f'      set description of ev to "{_esc(changes["notes"])}"')
    pre_block = ("\n".join(pre) + "\n") if pre else ""
    body = "\n".join(sets)
    return f'''tell application "Calendar"
  tell {_cal_clause(calendar)}
{pre_block}    repeat with ev in (every event whose uid is "{_esc(uid)}")
{body}
    end repeat
  end tell
end tell'''


def _script_delete(calendar, uid) -> str:
    return f'''tell application "Calendar"
  tell {_cal_clause(calendar)}
    delete (every event whose uid is "{_esc(uid)}")
  end tell
end tell'''


def _script_list_calendars() -> str:
    return '''tell application "Calendar"
  set out to ""
  repeat with c in (every calendar whose writable is true)
    set out to out & (name of c) & linefeed
  end repeat
  return out
end tell'''


def list_calendars() -> list:
    """回可寫入的日曆名清單（去重；Calendar 可能回同名重複）。列舉遠端日曆慢（~22s）→ 放寬逾時。"""
    raw = _run(_script_list_calendars(), timeout=45)
    seen, out = set(), []
    for ln in (raw or "").splitlines():
        name = ln.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ── 執行 + 公開介面 ───────────────────────────────────────────
def _run(script: str, timeout: int = 20) -> str:
    """執行 AppleScript，回 stdout（去尾換行）。失敗丟 RuntimeError。"""
    if sys.platform != "darwin":
        raise RuntimeError("行事曆動作僅支援 macOS（AppleScript）")
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"osascript 失敗：{r.stderr.strip()}")
    return r.stdout.rstrip("\n")


def _cal(calendar):
    return calendar if calendar is not None else config.CALENDAR_NAME


def create_event(title, start, end, notes="", calendar=None, all_day=False) -> dict:
    uid = _run(_script_create(_cal(calendar), title, start, end, notes, all_day))
    return {"uid": uid, "title": title, "start": start, "end": end}


def list_events(start, end, calendar=None) -> list:
    return _parse_events(_run(_script_list(_cal(calendar), start, end)))


def update_event(uid, changes: dict, calendar=None) -> dict:
    _run(_script_update(_cal(calendar), uid, changes))
    return {"updated": True, "uid": uid}


def delete_event(uid, calendar=None) -> dict:
    _run(_script_delete(_cal(calendar), uid))
    return {"deleted": True}
