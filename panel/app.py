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

import webbrowser
from pathlib import Path

import config
import llm
import leave_digest
import focus_draft
import memory
import user_profile
from panel import botctl, env_io, libreoffice, uninstall
import analysis
import browse_allowlist
import browse_launch
from db.connection import get_conn, apply_schema
from ingest.obsidian import ingest_dir, count_md_files
from ingest.github import commit_to_chunk
from ingest.self_doc import seed as seed_self_doc
from github_sync import _fetch_commits, gh_ready, list_repos

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
    botctl.log_event("💾 已儲存身份設定")
    return jsonify({"ok": True})


@app.post("/api/bot/<action>")
def api_bot(action):
    _label = {"start": "▶️ 控制台啟動 bot", "stop": "🛑 控制台停止 bot", "restart": "🔄 控制台重啟 bot"}
    if action not in _label:
        return jsonify({"error": "bad action"}), 400
    if action in ("start", "restart"):       # 啟動前 pre-flight：缺必要設定就擋下，回原因給前端提示
        problems = botctl.preflight_errors()
        if problems:
            botctl.log_event("⛔ 啟動被擋（缺設定）：" + "；".join(problems))
            return jsonify({"ok": False, "running": botctl.is_running(), "problems": problems})
    botctl.log_event(_label[action])      # 寫進 bot.log，即時 Log 看得到是誰按的
    {"start": botctl.start, "stop": botctl.stop, "restart": botctl.restart}[action]()
    if action in ("start", "restart"):
        # 同步刷新「面板自己」的 config（金鑰/模型）—— 面板的 config 是開機時載入的、不會自動重讀；
        # 不刷的話狀態列/列模型仍顯示舊值，使用者只好整個關掉面板重開。
        config.reload_runtime_keys()
        llm.reset_clients()
    return jsonify({"ok": True, "running": botctl.is_running()})


@app.get("/api/leave")
def api_leave_get():
    return jsonify(env_io.read_leave())


@app.post("/api/leave")
def api_leave_post():
    d = request.get_json(force=True)
    env_io.write_leave(d.get("leave_start", ""), d.get("leave_end", ""), d.get("focus", ""))
    botctl.log_event("💾 已儲存請假／本週重點")
    return jsonify({"ok": True})


@app.post("/api/leave/digest")
def api_leave_digest():
    """彙整請假期間同事項目+待辦 → 面板顯示並一併發 owner TG。容錯不 500。"""
    try:
        result = leave_digest.compile_digest(model=env_io.read_models()["code"])
        if result.get("ok") and result.get("summary"):
            result["tg_sent"] = leave_digest.send_to_owner("📋 請假期間彙整：\n\n" + result["summary"])
            botctl.log_event("📋 請假彙整已產生" + ("並發送至 TG" if result.get("tg_sent") else "（未發送）"))
        return jsonify(result)
    except Exception:
        botctl.log_event("⚠️ 請假彙整失敗")
        return jsonify({"ok": False, "error": "彙整失敗，請稍後再試 🙏"})


@app.post("/api/leave/focus-draft")
def api_leave_focus_draft():
    """用高階模型從近期素材擬一份本週重點草稿（填入欄位供編修）。容錯不 500。"""
    try:
        d = request.get_json(force=True) or {}
        return jsonify(focus_draft.draft(d.get("brief", ""), model=env_io.read_models()["code"]))
    except Exception:
        return jsonify({"ok": False, "error": "擬稿失敗，請稍後再試 🙏"})


@app.get("/api/allowlist")
def api_allow_get():
    return jsonify({"entries": env_io.read_allowlist()})


@app.post("/api/allowlist")
def api_allow_post():
    d = request.get_json(force=True)
    entries = d.get("entries", [])
    env_io.write_allowlist(entries)
    botctl.log_event(f"👥 白名單更新（{len(entries)} 人）")
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
    botctl.log_event(f"🌐 瀏覽網域白名單更新（{len(domains)} 個）")
    return jsonify({"ok": True})


@app.get("/api/browse/enabled")
def api_browse_enabled_get():
    return jsonify({"enabled": env_io.read_browse_enabled()})


@app.get("/api/browse/ready")
def api_browse_ready_get():
    # 瀏覽元件是否已就緒 / 正在背景安裝。前端據此決定提示下載或繼續輪詢。
    return jsonify(browse_launch.install_status())


@app.post("/api/browse/install")
def api_browse_install_post():
    # 背景下載瀏覽器元件（~150MB），非阻塞。前端先跳確認、確定才打這支，再輪詢 ready。
    r = browse_launch.start_install()
    if r.get("started"):
        botctl.log_event("⬇️ 開始安裝瀏覽元件（Chromium ~150MB，背景）")
    return jsonify(r)


@app.post("/api/browse/enabled")
def api_browse_enabled_post():
    d = request.get_json(force=True) or {}
    enabled = bool(d.get("enabled"))
    env_io.write_browse_enabled(enabled)
    botctl.log_event(f"🌐 網站瀏覽：{'ON' if enabled else 'OFF'}")
    result = {"ok": True, "enabled": enabled}
    try:
        if enabled:                              # 啟用時順手開專用 Chromium（帶遠端偵錯）
            result["browser_ready"] = browse_launch.launch()
        else:                                    # 停用時關閉專用 Chromium（不動個人 Chrome）
            browse_launch.shutdown()
    except Exception:
        result["browser_ready"] = False
    return jsonify(result)


@app.post("/api/browse/login/begin")
def api_browse_login_begin():
    """開可見視窗供使用者登入網站（headed）。容錯不 500。"""
    try:
        return jsonify({"ok": True, "ready": browse_launch.begin_login()})
    except Exception:
        return jsonify({"ok": False, "ready": False})


@app.post("/api/browse/login/end")
def api_browse_login_end():
    """登入完成，收掉視窗回 headless。容錯不 500。"""
    try:
        browse_launch.end_login()
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False})


@app.get("/api/browse/login/status")
def api_browse_login_status():
    return jsonify({"login_mode": browse_launch.is_login_mode()})


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
    botctl.log_event("💾 已儲存知識來源（Obsidian / GitHub repos / 程式碼母資料夾）")
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


@app.get("/api/provider-models")
def api_provider_models():
    """列出有設金鑰之供應商的對話模型（Google/Anthropic/OpenAI），供模型路由 picker。容錯不 500。
    先即時從 .env 刷新金鑰並清 client 快取 → 面板剛存的金鑰免重啟面板即生效。"""
    try:
        config.reload_runtime_keys()   # config 在面板啟動時載入、不會自動重讀；存金鑰後在此即時刷新
        llm.reset_clients()            # 清快取 client，改用新金鑰/端點重建
        return jsonify(llm.list_available_models())
    except Exception:
        return jsonify({"models": [], "providers": {}})


@app.get("/api/actions")
def api_actions_get():
    return jsonify(env_io.read_actions())


@app.post("/api/actions")
def api_actions_post():
    d = request.get_json(force=True) or {}
    a_on, e_on, m_on, s_on = (bool(d.get("enabled")), bool(d.get("email_enabled")),
                              bool(d.get("media_enabled")), bool(d.get("search_enabled")))
    env_io.write_actions(a_on, d.get("calendar_name", ""), e_on, d.get("mail_account", ""), m_on, s_on)
    _ss = lambda b: "ON" if b else "OFF"
    botctl.log_event(f"⚙️ 動作工具：行事曆 {_ss(a_on)}・收發信 {_ss(e_on)}・媒體 {_ss(m_on)}・時事搜尋 {_ss(s_on)}")
    return jsonify({"ok": True})


@app.get("/api/image-gen/enabled")
def api_image_gen_get():
    return jsonify({"enabled": env_io.read_image_gen_enabled()})


@app.post("/api/image-gen/enabled")
def api_image_gen_post():
    d = request.get_json(force=True) or {}
    en = bool(d.get("enabled"))
    env_io.write_image_gen_enabled(en)
    botctl.log_event(f"🖼️ 自動配圖：{'ON' if en else 'OFF'}")
    return jsonify({"ok": True})


@app.get("/api/libreoffice")
def api_libreoffice_get():
    return jsonify(libreoffice.status())


@app.post("/api/libreoffice/install")
def api_libreoffice_install():
    r = libreoffice.start_install()
    if r.get("started"):
        botctl.log_event("⬇️ 開始安裝 LibreOffice（背景）")
    return jsonify(r)


@app.get("/api/uninstall/scan")
def api_uninstall_scan():
    return jsonify(uninstall.scan())


@app.post("/api/uninstall/remove")
def api_uninstall_remove():
    if botctl.is_running():        # 模型/檔案可能還在使用、檔案鎖佔用 → 先停 bot 才安全
        return jsonify({"ok": False, "error": "請先停止 bot 再卸載（模型/檔案可能還在使用中）"})
    body = request.get_json(silent=True) or {}
    paths = body.get("paths") or []
    clear_data = bool(body.get("clearData"))
    botctl.log_event(f"🗑️ 解除安裝：移除 {len(paths)} 項元件" + ("＋清除 JAYVIS 資料" if clear_data else ""))
    r = uninstall.remove(paths, clear_data)
    return jsonify({"ok": True, **r})


@app.post("/api/quit")
def api_quit():
    """關閉整個 JAYVIS 應用（pywebview 視窗）。供解除安裝後選擇性關閉用；bot 已要求先停止。"""
    botctl.log_event("👋 關閉 JAYVIS（解除安裝後）")

    def _close():
        try:
            import browse_launch                 # 順手收掉面板自己拉起的專屬 Chromium，避免孤兒
            browse_launch.suspend_watchdog()
            browse_launch.shutdown()
        except Exception:
            pass
        try:
            import webview
            for w in list(getattr(webview, "windows", [])):
                try:
                    w.destroy()                  # 關窗 → webview.start() 返回 → 程序結束
                except Exception:
                    pass
        except Exception:
            pass

    threading.Timer(0.3, _close).start()         # 先把 HTTP 回應送出再關窗，避免前端 fetch 中斷
    return jsonify({"ok": True})


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
        botctl.clear_graduation()                          # 全部清掉 → 也重置「學士」畢業里程碑
        botctl.log_event("🗑️ 清除對談記憶：全部")
    elif d.get("person_id"):
        memory.clear(str(d["person_id"]))
        if str(d["person_id"]) == str(config.OWNER_CHAT_ID):   # 清掉 owner 本人 → 也重置畢業，回到一般重新成長
            botctl.clear_graduation()
        botctl.log_event(f"🗑️ 清除對談記憶：{d['person_id']}")
    return jsonify({"ok": True})


_mem_import = {"running": False, "last": ""}      # owner 聊天記憶匯入的背景進度


@app.post("/api/memory/export")
def api_memory_export():
    """匯出 owner 聊天記憶為 JAYVIS 格式 .json（原生另存對話框寫檔）。"""
    if not config.OWNER_CHAT_ID:
        return jsonify({"ok": False, "error": "尚未設定 OWNER_CHAT_ID（你的 TG id），無法匯出 owner 記憶"})
    if not webview.windows:
        return jsonify({"ok": False, "error": "需在桌面面板操作（無原生視窗）"}), 501
    data = memory.build_export(config.OWNER_CHAT_ID)
    if not data["turns"]:
        return jsonify({"ok": False, "error": "目前沒有可匯出的 owner 聊天記憶"})
    try:
        picked = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG, save_filename="jayvis-memory.json",
            file_types=("JAYVIS 記憶 (*.json)",))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 501
    path = picked if isinstance(picked, str) else (picked[0] if picked else "")
    if not path:
        return jsonify({"ok": False, "error": "已取消"})
    if not path.lower().endswith(".json"):
        path += ".json"
    Path(path).write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    botctl.log_event(f"💾 匯出 owner 聊天記憶（{len(data['turns'])} 則）")
    return jsonify({"ok": True, "path": path, "count": len(data["turns"])})


@app.post("/api/memory/import-pick")
def api_memory_import_pick():
    """原生檔案選擇器，限定 .json（JAYVIS 記憶檔）。回選到的路徑。"""
    if not webview.windows:
        return jsonify({"error": "需在桌面面板操作（無原生視窗）"}), 501
    try:
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG, file_types=("JAYVIS 記憶 (*.json)",))
    except Exception as e:
        return jsonify({"error": str(e)}), 501
    return jsonify({"path": result[0] if result else ""})


@app.post("/api/memory/import")
def api_memory_import():
    """讀選到的 .json → 嚴格驗證 JAYVIS 格式 → 背景逐則灌進 owner 記憶（走完整管線）。"""
    if not config.OWNER_CHAT_ID:
        return jsonify({"ok": False, "error": "尚未設定 OWNER_CHAT_ID（你的 TG id），無法匯入 owner 記憶"})
    if _mem_import["running"]:
        return jsonify({"ok": False, "error": "匯入進行中，請稍候"})
    d = request.get_json(silent=True) or {}
    path, clear_first = d.get("path", ""), bool(d.get("clearFirst"))
    rebuild = d.get("rebuild", True)                                       # 匯入後重建「長期認識」（用模型；可關）
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "找不到檔案"})
    try:
        data = _json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"ok": False, "error": "不是有效的 JSON 檔"})
    turns, err = memory.validate_import(data)
    if err:
        return jsonify({"ok": False, "error": "格式不符：" + err})          # 限定格式：非 JAYVIS 記憶檔一律擋
    owner_name = env_io.read_profile().get("owner_name") or None

    def _run():
        _mem_import.update(running=True, last=f"匯入中… 0/{len(turns)}")
        try:
            n = memory.import_turns(config.OWNER_CHAT_ID, turns, alias=owner_name,
                                    clear_first=clear_first,
                                    progress=lambda done, total: _mem_import.update(last=f"匯入中… {done}/{total}"))
            if rebuild and n:                                              # 從匯入內容重建長期認識（分窗用模型）
                _mem_import["last"] = "重建長期認識中…"
                import user_profile
                user_profile.rebuild_from_memory(
                    config.OWNER_CHAT_ID,
                    progress=lambda done, total: _mem_import.update(last=f"重建長期認識中… {done}/{total}"))
            _mem_import["last"] = f"✅ 完成：匯入 {n} 則" + ("＋已重建長期認識" if (rebuild and n) else "")
            botctl.log_event(f"📥 匯入 owner 聊天記憶（{n} 則{'，已先清空' if clear_first else ''}{'，已重建長期認識' if (rebuild and n) else ''}）")
        except Exception as e:
            _mem_import["last"] = f"匯入失敗：{e}"
        finally:
            _mem_import["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "started": True, "count": len(turns)})


@app.get("/api/memory/import-status")
def api_memory_import_status():
    return jsonify(_mem_import)


@app.get("/api/memory/profile")
def api_memory_profile():
    return jsonify({"profile": user_profile.get(str(config.OWNER_CHAT_ID))})


@app.post("/api/memory/profile/clear")
def api_memory_profile_clear():
    user_profile.clear(str(config.OWNER_CHAT_ID))
    botctl.log_event("🗑️ 清除 JAYVIS 對你的長期認識")
    return jsonify({"ok": True})


@app.get("/api/owner")
def api_owner_get():
    return jsonify(env_io.read_owner())


@app.post("/api/owner")
def api_owner_post():
    env_io.write_owner((request.get_json(force=True) or {}).get("owner_chat_id", ""))
    botctl.log_event("👤 已更新 owner TG id")
    return jsonify({"ok": True})


@app.get("/api/bot-token")
def api_bot_token_get():
    return jsonify({"set": env_io.read_bot_token_set()})


@app.post("/api/bot-token")
def api_bot_token_post():
    token = (request.get_json(force=True) or {}).get("token", "")
    env_io.write_bot_token(token)
    if (token or "").strip():
        botctl.log_event("🔑 已更新 Bot Token")     # 只記事件、不記 token 值
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
    keys = request.get_json(force=True) or {}
    env_io.write_llm_keys(keys)
    updated = [n for n in ("gemini", "anthropic", "openai", "tavily") if (keys.get(n) or "").strip()]
    if updated:
        botctl.log_event("🔑 已更新金鑰：" + "、".join(updated))   # 只記是哪幾家、不記金鑰值
    return jsonify({"ok": True})


@app.get("/api/models")
def api_models_get():
    return jsonify(env_io.read_models())


@app.post("/api/models")
def api_models_post():
    d = request.get_json(force=True)
    env_io.write_models(d.get("general"), d.get("code"), d.get("threshold"),
                        openai_base_url=d.get("openai_base_url"))
    botctl.log_event(f"💾 已儲存模型：一般={d.get('general') or '（空）'}・高階={d.get('code') or '（空）'}")
    return jsonify({"ok": True})


def _run_backfill(src):
    botctl.log_event(f"🔄 重建索引 {src} 開始…")
    try:
        conn = get_conn()
        apply_schema(conn)
        sd = 0
        try:
            sd = seed_self_doc(conn)        # JAYVIS 自我說明：隨 repo 出貨、任何重建都自動灌進 KB（使用者免手動搬檔）
            if sd:
                botctl.log_event(f"📘 自我說明：{sd} 段已同步進知識庫")
        except Exception as e:
            botctl.log_event(f"📘 自我說明同步略過：{e}")
        # 即時讀 .env：面板剛存的來源不必重啟 panel 就生效
        if src == "self":                   # 初始化「讓 JAYVIS 認識自己」：只灌自我說明，不需 Obsidian/GitHub
            msg = (f"JAYVIS 已認識自己（自我說明 {sd} 段進知識庫）——現在能回答自己的設定／功能了"
                   if sd else "⚠️ 找不到自我說明檔（docs/JAYVIS-使用說明.md）")
        elif src == "obsidian":
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
            if not repos:
                msg = "⚠️ github: 尚未設定任何 repo（每行一個 owner/repo）"
            else:
                ready, why = gh_ready()           # 只在有設 repo 時才檢查 gh（免跑多餘子行程）
                if not ready:                     # gh 沒裝/沒登入 → 明確說原因，別靜默回 0
                    msg = f"⚠️ github: {why}"
                else:
                    n, failed = 0, []
                    for repo in repos:
                        commits = _fetch_commits(repo)
                        if not commits:
                            failed.append(repo)
                        for c in commits:
                            rec = commit_to_chunk(conn, repo=repo, sha=c.get("sha", ""),
                                                  author=c.get("author", ""),
                                                  date=c.get("date", "")[:10], msg=c.get("msg", ""))
                            if rec.raw_text:
                                n += 1
                    if n == 0:
                        msg = "⚠️ github: 取不到任何 commit，請確認 repo 名稱(owner/repo)與 gh 帳號權限"
                    elif failed:
                        msg = f"github: 寫入 {n} chunks（這些 repo 取不到：{', '.join(failed)}）"
                    else:
                        msg = f"github: 寫入 {n} chunks"
        conn.close()
        _backfill["last"] = msg
        botctl.log_event(f"✅ 重建索引 {src}：{msg}")
    except Exception as e:
        _backfill["last"] = f"{src} 失敗: {e}"
        botctl.log_event(f"⚠️ 重建索引 {src} 失敗：{e}")
    finally:
        _backfill["running"] = False


@app.post("/api/backfill/<src>")
def api_backfill(src):
    if src not in ("obsidian", "github", "self"):
        return jsonify({"error": "bad src"}), 400
    if _backfill["running"]:
        return jsonify({"error": "已在執行"}), 409
    _backfill["running"] = True
    # 訊息含「認識自己」→ 前端把 self 的進度/結果顯示在按鈕下方（而非重建索引處）
    _backfill["last"] = "讓 JAYVIS 認識自己…" if src == "self" else f"{src} 執行中…"
    threading.Thread(target=_run_backfill, args=(src,), daemon=True).start()
    return jsonify({"started": True})


@app.get("/api/github/available-repos")
def api_github_available_repos():
    """gh 登入後列出帳號可存取的 repo，供面板「從 GitHub 帶入」勾選。未就緒回原因。"""
    ready, why = gh_ready()
    if not ready:
        return jsonify({"ok": False, "error": why})
    return jsonify({"ok": True, "repos": list_repos()})


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
    model = env_io.read_models()["code"]          # 即時讀 .env（程式高階模型）
    result = analysis.generate_report(q, model=model)
    if result.get("ok") and result.get("path"):
        try:
            # as_uri() 正確編碼路徑（vault 常含空格，如 iCloud「Mobile Documents」），否則瀏覽器打不開
            webbrowser.open(Path(result["path"]).as_uri())   # 生完自動用預設瀏覽器開啟
        except Exception:
            pass
        botctl.log_event(f"📊 分析報告 → {result.get('filename')}")
    else:
        botctl.log_event(f"📊 分析失敗：{result.get('error', '')}")
    return jsonify(result)


@app.post("/api/analyze/refine")
def api_analyze_refine():
    d = request.get_json(force=True)
    instruction = (d.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"error": "empty"}), 400
    model = env_io.read_models()["code"]          # 即時讀 .env（程式高階模型）
    result = analysis.refine_report(instruction, model=model)
    if result.get("ok") and result.get("path"):
        try:
            webbrowser.open(Path(result["path"]).as_uri())   # 修改完自動用預設瀏覽器開啟
        except Exception:
            pass
        botctl.log_event(f"📊 修改報告 → {result.get('filename')}")
    else:
        botctl.log_event(f"📊 修改失敗：{result.get('error', '')}")
    return jsonify(result)
