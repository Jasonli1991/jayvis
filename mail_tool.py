"""macOS Mail.app 操作（透過 osascript）。純函式產生 AppleScript、執行、解析。"""
import subprocess
import sys

import config

SEP = "\x1f"
MAX_BODY = 2000     # 讀信內文截斷，避免 prompt 爆
MAX_SCAN = 25       # list_inbox 最多掃幾封（slice 限縮，避免整匣 materialize）


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _run(script: str) -> str:
    if sys.platform != "darwin":
        raise RuntimeError("收發信僅支援 macOS（AppleScript）")
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=45)
    if r.returncode != 0:
        raise RuntimeError(f"osascript 失敗：{r.stderr.strip()}")
    return r.stdout.rstrip("\n")


def _script_send(to, subject, body, account="") -> str:
    sender = f'  set sender of newMsg to "{_esc(account)}"\n' if account else ""
    return f'''tell application "Mail"
  set newMsg to make new outgoing message with properties {{subject:"{_esc(subject)}", content:"{_esc(body)}", visible:false}}
  tell newMsg
    make new to recipient at end of to recipients with properties {{address:"{_esc(to)}"}}
  end tell
{sender}  send newMsg
end tell'''


def send_mail(to, subject, body, account="") -> dict:
    _run(_script_send(to, subject, body, account))
    return {"sent": True}


def _script_list_inbox(scope, n) -> str:
    # slice 限縮（避免整匣 materialize）+ 逐封存取（unified inbox 批次取 id 會壞）。
    filt = "    if (read status of m) then set okMsg to false\n" if scope == "unread" else ""
    return f'''tell application "Mail"
  try
    set theMsgs to messages 1 thru {MAX_SCAN} of inbox
  on error
    set theMsgs to messages of inbox
  end try
  set out to ""
  set found to 0
  repeat with m in theMsgs
    set okMsg to true
{filt}    if okMsg then
      set out to out & (id of m as string) & "{SEP}" & (sender of m) & "{SEP}" & (subject of m) & "{SEP}" & (date received of m as string) & linefeed
      set found to found + 1
      if found ≥ {int(n)} then exit repeat
    end if
  end repeat
  return out
end tell'''


def _parse_msgs(raw: str) -> list:
    out = []
    for ln in (raw or "").splitlines():
        p = ln.split(SEP)
        if len(p) == 4:
            out.append({"id": p[0], "from": p[1], "subject": p[2], "date": p[3]})
    return out


def list_inbox(scope="unread", n=10) -> list:
    return _parse_msgs(_run(_script_list_inbox(scope, n)))


def _script_read(msg_id) -> str:
    return f'''tell application "Mail"
  set m to first message of inbox whose id is {int(msg_id)}
  set b to content of m
  if (count of characters of b) > {MAX_BODY} then set b to (text 1 thru {MAX_BODY} of b)
  return (sender of m) & "{SEP}" & (subject of m) & "{SEP}" & b
end tell'''


def read_message(msg_id) -> dict:
    p = _run(_script_read(msg_id)).split(SEP, 2)
    return {"from": p[0], "subject": p[1] if len(p) > 1 else "", "body": p[2] if len(p) > 2 else ""}


def _script_list_accounts() -> str:
    return '''tell application "Mail"
  set out to ""
  repeat with a in accounts
    set ea to email addresses of a
    if ea is not missing value then
      repeat with addr in ea
        set out to out & (addr as text) & linefeed
      end repeat
    end if
  end repeat
  return out
end tell'''


def list_accounts() -> list:
    seen, res = set(), []
    for ln in _run(_script_list_accounts()).splitlines():
        a = ln.strip()
        if a and a not in seen:
            seen.add(a)
            res.append(a)
    return res


def _script_delete(msg_id) -> str:
    return f'''tell application "Mail"
  delete (first message of inbox whose id is {int(msg_id)})
end tell'''


def delete_message(msg_id) -> dict:
    _run(_script_delete(msg_id))     # Mail 的 delete = 移到垃圾桶（可復原）
    return {"deleted": True}
