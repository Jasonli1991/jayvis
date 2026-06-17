import ipaddress
import json as _json
import logging
import os
import socket
import threading
import urllib.request
from urllib.parse import urlparse

from dotenv import load_dotenv, get_key
load_dotenv()

# 面板每幾秒輪詢 /api/logs、/api/status，werkzeug 預設會把每筆存取印到終端 → 噪音，靜音它
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import webview
from flask import Flask, jsonify, request, send_from_directory

import config
import memory
import user_profile
from panel import botctl, env_io, libreoffice
import analysis
import browse_allowlist
import browse_launch
from db.connection import get_conn, apply_schema
from ingest.obsidian import ingest_dir, count_md_files
from ingest.github import commit_to_chunk
from github_sync import _fetch_commits

app = Flask(__name__, static_folder="static", static_url_path="")

# ── 本機面板防護：擋瀏覽器跨來源請求（CSRF）與 DNS rebinding ──
# 面板綁 127.0.0.1，但瀏覽器裡的惡意網頁仍可對 localhost 發跨來源 POST
# （改金鑰/白名單/來源）。Host 白名單擋 rebinding；Origin 檢查擋 CSRF。
# 不帶 Origin 的本機工具（curl、測試、pywebview）照常放行。
_ALLOWED_HOSTS = {"127.0.0.1:8765", "localhost:8765", "127.0.0.1", "localhost"}
_ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}


@app.before_request
def _local_origin_guard():
    if request.host not in _ALLOWED_HOSTS:
        return jsonify({"error": "bad host"}), 403
    # 跨來源（任一方法，含 GET）帶不允許的 Origin → 擋。
    # 防惡意網站用跨來源請求驅動面板的憑證型端點（如 /api/verify-tg-id 用 bot token、
    # /api/llm-models?base= 的對外 fetch）。同源請求帶的是允許的 Origin 或不帶 → 放行。
    origin = request.headers.get("Origin")
    if origin and origin not in _ALLOWED_ORIGINS:
        return jsonify({"error": "cross-origin blocked"}), 403


@app.after_request
def _no_cache(resp):
    # 本機單人面板：永不快取，改了前端重啟即見（避免 WKWebView 顯示舊版）
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


_backfill = {"running": False, "last": ""}


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/status")
def api_status():
    s = botctl.status()
    s["backfill"] = _backfill
    s["owner_name"] = env_io.read_profile().get("owner_name", "")
    s["allowlist"] = len(env_io.read_allowlist())     # 即時計數（不必重啟 bot）
    _m = env_io.read_models()                          # 即時讀 .env（避免徽章顯示面板啟動時的舊模型）
    s["models"] = {"general": _m["general"], "code": _m["code"]}
    s["version"] = config.APP_VERSION
    return jsonify(s)


@app.get("/api/profile")
def api_profile_get():
    return jsonify(env_io.read_profile())


def _profile_is_empty(p) -> bool:
    """整份身份是否實質空白（assistant_name 是衍生欄位，不納入判斷）。"""
    if not isinstance(p, dict):
        return True
    scal = [str(p.get(k) or "").strip() for k in ("owner_name", "title", "company", "routing")]
    lst = [p.get(k) or [] for k in ("projects", "team", "bosses")]
    return not any(scal) and not any(lst)


@app.post("/api/profile")
def api_profile_post():
    p = request.get_json(force=True) or {}
    if _profile_is_empty(p):                       # 防呆：整份空白不覆蓋，避免誤清既有身份
        return jsonify({"ok": False, "reason": "整份身份是空的，未覆蓋（避免誤清）"}), 409
    env_io.write_profile(p)
    return jsonify({"ok": True})


@app.post("/api/bot/<action>")
def api_bot(action):
    _label = {"start": "▶️ 控制台啟動 bot", "stop": "🛑 控制台停止 bot", "restart": "🔄 控制台重啟 bot"}
    if action not in _label:
        return jsonify({"error": "bad action"}), 400
    botctl.log_event(_label[action])      # 寫進 bot.log，即時 Log 看得到是誰按的
    {"start": botctl.start, "stop": botctl.stop, "restart": botctl.restart}[action]()
    return jsonify({"running": botctl.is_running()})


@app.get("/api/leave")
def api_leave_get():
    return jsonify(env_io.read_leave())


@app.post("/api/leave")
def api_leave_post():
    d = request.get_json(force=True)
    env_io.write_leave(d.get("leave_start", ""), d.get("leave_end", ""), d.get("focus", ""))
    return jsonify({"ok": True})


@app.get("/api/allowlist")
def api_allow_get():
    return jsonify({"entries": env_io.read_allowlist()})


@app.post("/api/allowlist")
def api_allow_post():
    d = request.get_json(force=True)
    env_io.write_allowlist(d.get("entries", []))
    return jsonify({"ok": True})


@app.get("/api/browse/allowlist")
def api_browse_allow_get():
    return jsonify({"domains": browse_allowlist.load()})


@app.post("/api/browse/allowlist")
def api_browse_allow_post():
    d = request.get_json(force=True) or {}
    domains = d.get("domains", [])
    if not isinstance(domains, list):
        return jsonify({"error": "domains must be a list"}), 400
    browse_allowlist.save(domains)
    return jsonify({"ok": True})


@app.get("/api/browse/enabled")
def api_browse_enabled_get():
    return jsonify({"enabled": env_io.read_browse_enabled()})


@app.get("/api/browse/ready")
def api_browse_ready_get():
    # 瀏覽元件（playwright 套件 + Chromium）是否已安裝。前端據此決定要不要先提示下載。
    return jsonify({"ready": browse_launch.is_ready()})


@app.post("/api/browse/install")
def api_browse_install_post():
    # 下載瀏覽器元件（~150MB）。前端會先跳確認，使用者按確定才打這支。
    ok, log = browse_launch.install()
    return jsonify({"ok": ok, "log": log})


@app.post("/api/browse/enabled")
def api_browse_enabled_post():
    d = request.get_json(force=True) or {}
    enabled = bool(d.get("enabled"))
    env_io.write_browse_enabled(enabled)
    result = {"ok": True, "enabled": enabled}
    try:
        if enabled:                              # 啟用時順手開專用 Chromium（帶遠端偵錯）
            result["browser_ready"] = browse_launch.launch()
        else:                                    # 停用時關閉專用 Chromium（不動個人 Chrome）
            browse_launch.shutdown()
    except Exception:
        result["browser_ready"] = False
    return jsonify(result)


@app.post("/api/pick-folder")
def api_pick_folder():
    """喚起 pywebview 原生資料夾選擇器；無原生視窗（純瀏覽器開）回 501。"""
    if not webview.windows:
        return jsonify({"error": "no native window"}), 501
    d = request.get_json(silent=True) or {}
    start = d.get("start", "")
    directory = start if os.path.isdir(start) else os.path.expanduser("~")
    try:
        result = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG, directory=directory)
    except Exception as e:
        return jsonify({"error": str(e)}), 501
    return jsonify({"path": result[0] if result else ""})


@app.get("/api/sources")
def api_sources_get():
    return jsonify(env_io.read_sources())


@app.post("/api/sources")
def api_sources_post():
    d = request.get_json(force=True)
    env_io.write_sources(d.get("obsidian_path", ""), d.get("github_repos", []), d.get("code_root", ""))
    return jsonify({"ok": True})


def _safe_base(base: str) -> bool:
    """SSRF 防護：?base= 只允許 http/https + loopback / 私有區網（本地/公司 Ollama 用途）；
    擋掉 link-local（169.254，雲端 metadata）、外部位址、非 http scheme。
    （.env 設的端點不經此檢查 —— 那是 owner 經跨來源防護的 POST 寫入，可指第三方公開端點。）"""
    try:
        u = urlparse(base)
    except Exception:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except Exception:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        if not (ip.is_loopback or ip.is_private):
            return False                          # 只允許 loopback / 私有區網
    return True


def _fetch_compat_models(base: str) -> list:
    """打 OpenAI 相容端點的 GET /models，回排序後的 model id 清單（3 秒逾時）。"""
    url = base.rstrip("/") + "/models"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = _json.load(resp)
    return sorted(d["id"] for d in data.get("data", []) if d.get("id"))


@app.get("/api/llm-models")
def api_llm_models_get():
    """列出相容端點（如本地 Ollama）可選的模型；無端點/連不到 → 空清單，不卡、不 500。
    ?base=<url> 可帶當下欄位值（免先儲存就能預覽，但僅限本機/區網以防 SSRF）；沒帶則讀 .env。"""
    base_param = (request.args.get("base") or "").strip()
    if base_param:
        if not _safe_base(base_param):            # SSRF：?base 只放行本機/區網
            return jsonify({"models": [], "endpoint": base_param, "error": "blocked"})
        base = base_param
    else:
        base = (get_key(env_io.ENV_PATH, "OPENAI_BASE_URL") or "").strip()
    if not base:
        return jsonify({"models": [], "endpoint": ""})
    try:
        return jsonify({"models": _fetch_compat_models(base), "endpoint": base})
    except Exception:
        return jsonify({"models": [], "endpoint": base, "error": "unreachable"})


@app.get("/api/actions")
def api_actions_get():
    return jsonify(env_io.read_actions())


@app.post("/api/actions")
def api_actions_post():
    d = request.get_json(force=True) or {}
    env_io.write_actions(bool(d.get("enabled")), d.get("calendar_name", ""),
                         bool(d.get("email_enabled")), d.get("mail_account", ""),
                         bool(d.get("media_enabled")), bool(d.get("search_enabled")))
    return jsonify({"ok": True})


@app.get("/api/libreoffice")
def api_libreoffice_get():
    return jsonify(libreoffice.status())


@app.post("/api/libreoffice/install")
def api_libreoffice_install():
    return jsonify(libreoffice.start_install())


_name_cache = {}     # person_id → 解析出的名字（避免重複打 getChat）


def _resolve_person_name(pid, stored_alias):
    """把記憶裡的 person_id 解析成人看得懂的名字：
    已存別名 → owner 名 → 白名單別名 →（查不到才）Telegram getChat → 都沒有則 None（前端顯示 ID）。"""
    if stored_alias:
        return stored_alias
    if str(pid) == str(config.OWNER_CHAT_ID):
        return config.OWNER_NAME
    try:
        if int(pid) in config.ALLOWLIST_ALIASES:
            return config.ALLOWLIST_ALIASES[int(pid)]
    except (ValueError, TypeError):
        pass
    if pid in _name_cache:
        return _name_cache[pid]
    name = None
    token = config.TG_BOT_TOKEN
    if token:
        try:
            data = _tg_get_chat(token, str(pid))
            if data.get("ok"):
                r = data.get("result", {})
                name = " ".join(x for x in [r.get("first_name"), r.get("last_name")] if x).strip() \
                    or (("@" + r["username"]) if r.get("username") else None)
        except Exception:
            name = None
    _name_cache[pid] = name
    if name:
        try:
            memory.backfill_alias(pid, name)   # 存回去：下次免查、回想 prompt 也有名字
        except Exception:
            pass
    return name


@app.get("/api/memory/persons")
def api_memory_persons():
    ps = memory.persons()
    for p in ps:
        p["alias"] = _resolve_person_name(p["person_id"], p.get("alias"))
    return jsonify(ps)


@app.get("/api/memory/timeline")
def api_memory_timeline():
    person = request.args.get("person", "")
    return jsonify(memory.timeline(person))


@app.post("/api/memory/clear")
def api_memory_clear():
    d = request.get_json(force=True) or {}
    if d.get("all"):
        memory.clear_all()
    elif d.get("person_id"):
        memory.clear(str(d["person_id"]))
    return jsonify({"ok": True})


@app.get("/api/memory/profile")
def api_memory_profile():
    return jsonify({"profile": user_profile.get(str(config.OWNER_CHAT_ID))})


@app.post("/api/memory/profile/clear")
def api_memory_profile_clear():
    user_profile.clear(str(config.OWNER_CHAT_ID))
    return jsonify({"ok": True})


@app.get("/api/owner")
def api_owner_get():
    return jsonify(env_io.read_owner())


@app.post("/api/owner")
def api_owner_post():
    env_io.write_owner((request.get_json(force=True) or {}).get("owner_chat_id", ""))
    return jsonify({"ok": True})


@app.get("/api/bot-token")
def api_bot_token_get():
    return jsonify({"set": env_io.read_bot_token_set()})


@app.post("/api/bot-token")
def api_bot_token_post():
    env_io.write_bot_token((request.get_json(force=True) or {}).get("token", ""))
    return jsonify({"ok": True})


def _tg_get_chat(token: str, tg_id: str) -> dict:
    """打 Telegram getChat，回其 JSON（ok/result/error_code…）。固定 host，無 SSRF。"""
    url = f"https://api.telegram.org/bot{token}/getChat?chat_id={tg_id}"
    try:
        return _json.load(urllib.request.urlopen(url, timeout=5))
    except urllib.error.HTTPError as he:          # 400=查無此人、401=token 無效…
        try:
            return _json.load(he)
        except Exception:
            return {"ok": False}


@app.get("/api/verify-tg-id")
def api_verify_tg_id():
    """盡力驗證 TG user_id：查得到回名字；查不到/沒互動過 → 明說。token 不外洩。"""
    tg_id = (request.args.get("id") or "").strip()
    if not tg_id.isdigit():
        return jsonify({"ok": False, "reason": "bad_format"})
    token = get_key(env_io.ENV_PATH, "TG_BOT_TOKEN")
    if not token:
        return jsonify({"ok": False, "reason": "no_token"})
    try:
        data = _tg_get_chat(token, tg_id)
    except Exception:
        return jsonify({"ok": False, "reason": "error"})
    if data.get("ok"):
        c = data.get("result", {})
        name = " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x).strip()
        uname = ("@" + c["username"]) if c.get("username") else ""
        return jsonify({"ok": True, "name": name or uname or tg_id, "username": uname})
    if data.get("error_code") == 401:
        return jsonify({"ok": False, "reason": "bad_token"})
    return jsonify({"ok": False, "reason": "not_found"})


@app.get("/api/llm-keys")
def api_llm_keys_get():
    return jsonify(env_io.read_llm_keys())


@app.post("/api/llm-keys")
def api_llm_keys_post():
    env_io.write_llm_keys(request.get_json(force=True) or {})
    return jsonify({"ok": True})


@app.get("/api/models")
def api_models_get():
    return jsonify(env_io.read_models())


@app.post("/api/models")
def api_models_post():
    d = request.get_json(force=True)
    env_io.write_models(d.get("general"), d.get("code"), d.get("threshold"),
                        openai_base_url=d.get("openai_base_url"))
    return jsonify({"ok": True})


def _run_backfill(src):
    try:
        conn = get_conn()
        apply_schema(conn)
        # 即時讀 .env：面板剛存的來源不必重啟 panel 就生效
        if src == "obsidian":
            path = get_key(env_io.ENV_PATH, "OBSIDIAN_PATH") or config.OBSIDIAN_PATH
            n = ingest_dir(conn, path)
            scanned = count_md_files(path)
            if n > 0:
                msg = f"obsidian: 寫入 {n} chunks（掃描 {scanned} 檔）"
            elif scanned == 0:
                msg = "⚠️ obsidian: 路徑下找不到任何筆記，請確認 vault 路徑（需含 01_Wiki 等資料夾）"
            else:
                msg = f"obsidian: 已是最新（掃描 {scanned} 檔，內容無變化）"
        else:
            repos = config._parse_repos(get_key(env_io.ENV_PATH, "GITHUB_REPOS"))
            n = 0
            for repo in repos:
                for c in _fetch_commits(repo):
                    rec = commit_to_chunk(conn, repo=repo, sha=c.get("sha", ""),
                                          author=c.get("author", ""),
                                          date=c.get("date", "")[:10], msg=c.get("msg", ""))
                    if rec.raw_text:
                        n += 1
            msg = f"github: 寫入 {n} chunks"
        conn.close()
        _backfill["last"] = msg
    except Exception as e:
        _backfill["last"] = f"{src} 失敗: {e}"
    finally:
        _backfill["running"] = False


@app.post("/api/backfill/<src>")
def api_backfill(src):
    if src not in ("obsidian", "github"):
        return jsonify({"error": "bad src"}), 400
    if _backfill["running"]:
        return jsonify({"error": "已在執行"}), 409
    _backfill["running"] = True
    _backfill["last"] = f"{src} 執行中…"
    threading.Thread(target=_run_backfill, args=(src,), daemon=True).start()
    return jsonify({"started": True})


@app.get("/api/logs")
def api_logs():
    n = int(request.args.get("n", 200))
    return jsonify({"log": botctl.tail_log(n, clean=True)})


@app.post("/api/analyze")
def api_analyze():
    d = request.get_json(force=True)
    q = (d.get("query") or "").strip()
    if not q:
        return jsonify({"error": "empty"}), 400
    model = env_io.read_models()["code"]          # 即時讀 .env（改了不必重啟面板）
    result = analysis.analyze(q, model=model)
    preview = q[:30] + ("…" if len(q) > 30 else "")
    botctl.log_event(f"🔍 分析：{preview} → {len(str(result.get('answer', '')))} 字"
                     f"（{len(result.get('sources') or [])} 來源）")
    return jsonify(result)
