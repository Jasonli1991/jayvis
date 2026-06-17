const $ = (id) => document.getElementById(id);
const getJSON = (u) => fetch(u).then(r => r.json());
const postJSON = (u, b) => fetch(u, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b || {})})
  .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw Object.assign(new Error("HTTP " + r.status), {body: j}); return j; });

function flash(el, text) { el.textContent = "✓ " + text; el.classList.add("ok"); el.classList.remove("warn"); setTimeout(() => el.classList.remove("ok"), 2200); }
function warn(el, text) { el.textContent = text; el.classList.add("warn"); el.classList.remove("ok"); setTimeout(() => el.classList.remove("warn"), 3500); }
// 送出期間鎖按鈕 + 轉圈圖示，finally 還原 → 防重複送出、長操作有回饋
async function withBusy(btn, fn) {
  const ic = btn && btn.querySelector(".ic");
  if (btn) { btn.disabled = true; btn.setAttribute("aria-busy", "true"); if (ic) ic.classList.add("spin"); }
  try { return await fn(); }
  finally { if (btn) { btn.disabled = false; btn.removeAttribute("aria-busy"); if (ic) ic.classList.remove("spin"); } }
}
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// theme toggle (persisted in localStorage)
const _themeBtn = $("theme-toggle");
if (_themeBtn) _themeBtn.onclick = () => {
  const root = document.documentElement;
  const t = root.getAttribute("data-theme") === "light" ? "dark" : "light";
  root.classList.add("theme-switching");          // 切換瞬間關掉過渡 → 不卡頓
  root.setAttribute("data-theme", t);
  try { localStorage.setItem("panel-theme", t); } catch (e) {}
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("theme-switching")));
};

// owner profile (list fields use 名稱｜說明 per-line format)
const _lines = (arr, a, b) => (arr || []).map(x => b ? `${x[a]}｜${x[b] || ""}` : x[a]).join("\n");
const _parse = (s, a, b) => s.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
  const [x, y] = l.split("｜"); return b ? {[a]: (x || "").trim(), [b]: (y || "").trim()} : {[a]: (x || "").trim()};
});
async function loadProfile() {
  try {
    const p = await getJSON("/api/profile");
    $("pf-name").value = p.owner_name || ""; $("pf-title").value = p.title || "";
    $("pf-company").value = p.company || "";
    $("pf-projects").value = _lines(p.projects, "name", "desc");
    $("pf-team").value = _lines(p.team, "name", "role");
    $("pf-bosses").value = _lines(p.bosses, "name", "note");
    renderRouting(p.routing);
  } catch (e) {
    warn($("pf-msg"), "身份載入失敗，請重整面板（資料未遺失）");  // 不靜靜留空、誤判成資料不見
  }
}

// ── 轉介規則：互動列（領域 → 負責人，負責人有團隊建議下拉）──
function _assigneeCandidates() {
  const names = [];
  const grab = (id) => ($(id).value || "").split("\n").forEach(l => {
    const n = l.split("｜")[0].trim(); if (n) names.push(n);
  });
  grab("pf-team"); grab("pf-bosses");
  return [...new Set(names)];
}

function _attachSuggest(input, getItems) {
  const wrap = input.closest(".r-person-wrap");
  const menu = document.createElement("div");
  menu.className = "model-menu"; menu.hidden = true;
  wrap.appendChild(menu);
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const items = getItems().filter(m => m.toLowerCase().includes(q));
    menu.innerHTML = "";
    if (!items.length) { menu.hidden = true; return; }
    items.forEach(m => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "model-opt"; b.textContent = m;
      b.onmousedown = (e) => { e.preventDefault(); input.value = m; menu.hidden = true; };
      menu.appendChild(b);
    });
    menu.hidden = false;
  };
  input.addEventListener("focus", render);
  input.addEventListener("input", render);
  input.addEventListener("blur", () => setTimeout(() => { menu.hidden = true; }, 150));
}

function _routingRow(area = "", person = "") {
  const row = document.createElement("div");
  row.className = "routing-row";
  row.innerHTML = '<input class="r-area" placeholder="領域（如：爬蟲）">' +
    '<span class="r-arrow">→</span>' +
    '<span class="r-person-wrap"><input class="r-person" placeholder="負責人" autocomplete="off"></span>' +
    '<button class="r-del" type="button" title="刪除">✕</button>';
  row.querySelector(".r-area").value = area;
  row.querySelector(".r-person").value = person;
  row.querySelector(".r-del").onclick = () => row.remove();
  _attachSuggest(row.querySelector(".r-person"), _assigneeCandidates);
  return row;
}

function renderRouting(str) {
  const box = $("pf-routing-rows"); box.innerHTML = "";
  (str || "").split(/[；;]/).map(s => s.trim()).filter(Boolean).forEach(part => {
    const [area, person] = part.split(/→|->/).map(x => (x || "").trim());
    box.appendChild(_routingRow(area || "", person || ""));
  });
  if (!box.children.length) box.appendChild(_routingRow());
}

function collectRouting() {
  return [...$("pf-routing-rows").querySelectorAll(".routing-row")]
    .map(r => [r.querySelector(".r-area").value.trim(), r.querySelector(".r-person").value.trim()])
    .filter(([a]) => a)
    .map(([a, p]) => p ? `${a} → ${p}` : a)
    .join("；");
}

$("pf-routing-add").onclick = () => $("pf-routing-rows").appendChild(_routingRow());
$("pf-save").onclick = () => withBusy($("pf-save"), async () => {
  const name = $("pf-name").value.trim(), title = $("pf-title").value.trim(), company = $("pf-company").value.trim();
  const projects = _parse($("pf-projects").value, "name", "desc");
  const team = _parse($("pf-team").value, "name", "role");
  const bosses = _parse($("pf-bosses").value, "name", "note");
  const routing = collectRouting();
  const routingEmpty = !routing || (Array.isArray(routing) ? !routing.length : !String(routing).trim());
  if (!name && !title && !company && !projects.length && !team.length && !bosses.length && routingEmpty) {
    warn($("pf-msg"), "表單是空的，沒有儲存（避免覆蓋既有身份）");  // 前端防呆
    return;
  }
  try {
    const p = await getJSON("/api/profile");
    Object.assign(p, {
      owner_name: name, title, company, assistant_name: (name || "") + " 的助理",
      projects, team, bosses, routing,
    });
    const res = await postJSON("/api/profile", p);
    if (res && res.ok === false) {                                // 後端防呆退回
      warn($("pf-msg"), "未儲存：" + (res.reason || "整份是空的"));
      return;
    }
    flash($("pf-msg"), "已儲存（重啟 bot 生效）");
  } catch (e) { warn($("pf-msg"), "儲存失敗，請重試"); }
});

async function refreshStatus() {
  const s = await getJSON("/api/status");
  $("dot").className = "dot " + (s.running ? "on" : "off");
  $("botstate").textContent = s.running ? "運行中" : "已停止";
  // 運行中 → 停用「啟動」；停止 → 停用「停止/重啟」
  document.querySelectorAll(".botbtns button").forEach(x => { x.disabled = x.dataset.act === "start" ? s.running : !s.running; });
  $("models").textContent = (s.models.general || "?").split("-").pop() + " / " + (s.models.code || "?").split("-").pop();
  const _memLabel = {conversation: "對話索引", action: "動作", git: "git", obsidian: "obsidian"};
  $("mem").textContent = Object.entries(s.memory || {}).map(([k, v]) => `${_memLabel[k] || k} ${v}`).join("、") || "—";
  $("allowcount").textContent = s.allowlist;
  if (s.owner_name) {
    document.querySelector(".brand-mark").textContent = s.owner_name.trim().charAt(0).toUpperCase();
    document.querySelector(".brand-name").textContent = s.owner_name + " 的個人 AI 助理";
  }
  if (s.version) $("ver").textContent = "v" + s.version;
  if (s.backfill && s.backfill.last) $("bf-msg").textContent = s.backfill.last;
}

const _escHtml = (s) => s.replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));

function _logLineHtml(raw) {
  const body = _escHtml(raw).replace(/^INFO:[\w.]+:/, "");   // 去掉 INFO:logger: 噪音前綴（已先轉義）
  let cls = "log-dim";
  if (/error|traceback|exception|失敗|❌|抱歉/i.test(raw)) cls = "log-err";
  else if (/LLM call|chat\/completions|generateContent/i.test(raw)) cls = "log-llm";
  else if (/✅|啟動/.test(raw)) cls = "log-ok";
  else if (/^WARNING|⚠️/i.test(raw)) cls = "log-warn";
  return `<span class="ll ${cls}">${body || "&nbsp;"}</span>`;
}

async function refreshLog() {
  const d = await getJSON("/api/logs?n=200");
  const el = $("log");
  el.innerHTML = (d.log || "—").split("\n").map(_logLineHtml).join("");
  el.scrollTop = el.scrollHeight;
}

// bot controls：點擊時鎖全部 + 轉圈 + 狀態文字，POST 後立即刷新；失敗有提示
document.querySelectorAll(".botbtns button").forEach(b =>
  b.onclick = async () => {
    const act = b.dataset.act, btns = [...document.querySelectorAll(".botbtns button")];
    btns.forEach(x => x.disabled = true);
    const ic = b.querySelector(".ic"); if (ic) ic.classList.add("spin");
    $("botstate").textContent = {start: "啟動中…", stop: "停止中…", restart: "重啟中…"}[act] || "處理中…";
    try { await postJSON("/api/bot/" + act); }
    catch (e) { $("botstate").textContent = "操作失敗，請看 Log"; }
    finally { if (ic) ic.classList.remove("spin"); await refreshStatus(); }
  });

// leave — custom date-range calendar
const calState = {start: null, end: null, view: null};
// local-date ISO (avoid toISOString UTC shift)
const _iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const _parseISO = s => { const [y, m, dd] = (s || "").split("-").map(Number); return (y && m && dd) ? new Date(y, m - 1, dd) : null; };
const PRESETS = [["今天", 0, 0], ["明天起 3 天", 1, 3], ["近 7 天", 0, 6], ["近 14 天", 0, 13]];

function _renderRangeText() {
  $("lv-range-txt").textContent = (calState.start && calState.end)
    ? `${_iso(calState.start)} ～ ${_iso(calState.end)}` : "點選日期區間";
}

function renderCal() {
  const base = calState.view || calState.start || new Date();
  const y = base.getFullYear(), m = base.getMonth();
  const startDow = (new Date(y, m, 1).getDay() + 6) % 7;     // 週一起
  const days = new Date(y, m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push("<span></span>");
  for (let d = 1; d <= days; d++) {
    const cur = new Date(y, m, d);
    const inRange = calState.start && calState.end && cur >= calState.start && cur <= calState.end;
    const isEnd = (calState.start && +cur === +calState.start) || (calState.end && +cur === +calState.end);
    cells.push(`<button type="button" class="cal-d${isEnd ? " sel" : inRange ? " in" : ""}" data-d="${_iso(cur)}">${d}</button>`);
  }
  $("cal").innerHTML = `
    <div class="cal-presets">${PRESETS.map((p, i) => `<button type="button" data-p="${i}">${p[0]}</button>`).join("")}</div>
    <div class="cal-head"><button type="button" id="cal-prev">‹</button><b>${y} 年 ${m + 1} 月</b><button type="button" id="cal-next">›</button></div>
    <div class="cal-dow">${["一", "二", "三", "四", "五", "六", "日"].map(x => `<span>${x}</span>`).join("")}</div>
    <div class="cal-grid">${cells.join("")}</div>
    <div class="cal-foot"><button type="button" id="cal-clear" class="btn ghost">清除</button><button type="button" id="cal-apply" class="btn primary">套用</button></div>`;
  $("cal").querySelectorAll(".cal-d").forEach(b => b.onclick = () => pickDay(_parseISO(b.dataset.d)));
  $("cal-prev").onclick = () => { calState.view = new Date(y, m - 1, 1); renderCal(); };
  $("cal-next").onclick = () => { calState.view = new Date(y, m + 1, 1); renderCal(); };
  $("cal-clear").onclick = () => { calState.start = calState.end = null; _renderRangeText(); renderCal(); };
  $("cal-apply").onclick = () => { $("cal").hidden = true; loadLeaveStatusPreview(); };
  $("cal").querySelectorAll("[data-p]").forEach(b => b.onclick = () => applyPreset(PRESETS[+b.dataset.p]));
}

function pickDay(d) {
  if (!calState.start || (calState.start && calState.end)) { calState.start = d; calState.end = null; }
  else if (d < calState.start) { calState.end = calState.start; calState.start = d; }
  else calState.end = d;
  _renderRangeText(); renderCal();
}
function applyPreset([, offStart, span]) {
  const s = new Date(); s.setHours(0, 0, 0, 0); s.setDate(s.getDate() + offStart);
  const e = new Date(s); e.setDate(s.getDate() + span);
  calState.start = s; calState.end = e; calState.view = new Date(s); _renderRangeText(); renderCal();
}
function loadLeaveStatusPreview() {
  const t = new Date(); t.setHours(0, 0, 0, 0);
  $("lv-status").value = (calState.start && calState.end && t >= calState.start && t <= calState.end)
    ? `請假中（${_iso(calState.start)} ~ ${_iso(calState.end)}）` : "在職中（目前無排定請假）";
}
$("lv-range").onclick = () => { const c = $("cal"); c.hidden = !c.hidden; if (!c.hidden) renderCal(); };
// 用 pointerdown 而非 click：點日期會觸發 renderCal() 重繪，click 冒泡到 document 時
// 原按鈕已脫離 DOM，contains() 會誤判成「點在外面」而收起日曆
document.addEventListener("pointerdown", (e) => {
  const c = $("cal");
  if (!c.hidden && !c.contains(e.target) && !$("lv-range").contains(e.target)) c.hidden = true;
});

async function loadLeave() {
  const d = await getJSON("/api/leave");
  $("lv-status").value = d.status || ""; $("lv-focus").value = d.focus || "";
  calState.start = _parseISO(d.leave_start); calState.end = _parseISO(d.leave_end); _renderRangeText();
}
$("lv-save").onclick = () => withBusy($("lv-save"), async () => {
  try {
    await postJSON("/api/leave", {
      leave_start: calState.start ? _iso(calState.start) : "",
      leave_end: calState.end ? _iso(calState.end) : "",
      focus: $("lv-focus").value,
    });
    flash($("lv-msg"), "已儲存（重啟 bot 生效）"); loadLeave();
  } catch (e) { warn($("lv-msg"), "儲存失敗，請重試"); }
});

// telegram：bot token（遮罩）+ owner id
async function loadBotToken() {
  const t = await getJSON("/api/bot-token");
  const el = $("bot-token");
  el.value = ""; el.placeholder = t.set ? "已設定 ••••••••" : "未設定";
  const o = await getJSON("/api/owner");
  $("owner-id").value = o.owner_chat_id || "";
}
$("tg-save").onclick = () => withBusy($("tg-save"), async () => {
  try {
    await postJSON("/api/owner", {owner_chat_id: $("owner-id").value.trim()});
    const v = $("bot-token").value.trim();
    if (v) await postJSON("/api/bot-token", {token: v});   // 遮罩：留空＝不變更
    flash($("bot-token-msg"), "已儲存（重啟 bot 生效）");
    loadBotToken();
  } catch (e) { warn($("bot-token-msg"), "儲存失敗，請重試"); }
});

// 動作工具（owner-only 行事曆）
async function loadActions() {
  const a = await getJSON("/api/actions");
  $("ac-enabled").checked = !!a.enabled;
  $("ac-cal").value = a.calendar_name || "";
  $("ac-email").checked = !!a.email_enabled;
  $("ac-mail-acct").value = a.mail_account || "";
  $("ac-media").checked = !!a.media_enabled;
  $("ac-search").checked = !!a.search_enabled;
}

// LibreOffice（文件轉檔）一鍵安裝
function renderLibre(s) {
  const st = $("lo-status"), btn = $("lo-install");
  if (s.installed) { st.textContent = "✓ LibreOffice 已安裝（可轉 Word/PDF）"; btn.style.display = "none"; }
  else if (s.installing) { st.textContent = "LibreOffice 安裝中…（背景下載約 700MB，請稍候）"; btn.style.display = "none"; setTimeout(loadLibre, 5000); }
  else if (!s.has_brew) { st.textContent = "未偵測到 Homebrew，無法一鍵安裝（圖片功能不受影響）"; btn.style.display = "none"; }
  else { st.textContent = "文件轉檔（Word/PDF）需要 LibreOffice"; btn.style.display = ""; }
}
async function loadLibre() { renderLibre(await getJSON("/api/libreoffice")); }

// 記憶（唯讀檢視 + 清除）
async function loadMemPersons() {
  const ps = await getJSON("/api/memory/persons");
  const sel = $("mem-person");
  const cur = sel.value;                                              // 記住目前選的對象
  sel.innerHTML = ps.map(p => `<option value="${esc(p.person_id)}">${esc(p.alias || p.person_id)}（${esc(p.count)}）</option>`).join("");
  if (cur && [...sel.options].some(o => o.value === cur)) sel.value = cur;  // 還原選擇，不跳掉
  loadMemTimeline();
}
async function loadMemTimeline() {
  const pid = $("mem-person").value;
  if (!pid) { $("mem-timeline").innerHTML = ""; return; }
  const tl = await getJSON("/api/memory/timeline?person=" + encodeURIComponent(pid));
  $("mem-timeline").innerHTML = tl.map(m =>
    `<li><span class="hint">${esc(m.ts)}・${esc(m.kind)}</span><br>${esc(m.content)}</li>`).join("") || "<li class='hint'>（無記錄）</li>";
}
$("mem-person").onchange = loadMemTimeline;
$("mem-person").addEventListener("focus", loadMemPersons);   // 點開下拉時重抓對談記憶（含時間軸）→ 免按鈕、免定時、不跟「重啟」混淆
$("mem-clear-one").onclick = async () => {
  const pid = $("mem-person").value; if (!pid) return;
  const label = $("mem-person").selectedOptions[0]?.textContent || pid;
  if (!confirm("確定清除「" + label + "」的對談記憶？")) return;
  try { await postJSON("/api/memory/clear", {person_id: pid}); flash($("mem-msg"), "已清除"); loadMemPersons(); }
  catch (e) { warn($("mem-msg"), "清除失敗"); }
};
$("mem-clear-all").onclick = async () => {
  if (!confirm("確定清除全部記憶？")) return;
  await postJSON("/api/memory/clear", {all: true});
  flash($("mem-msg"), "已全部清除"); loadMemPersons();
};
$("lo-install").onclick = async () => {
  $("lo-status").textContent = "開始安裝…";
  await postJSON("/api/libreoffice/install", {});
  setTimeout(loadLibre, 1500);
};
$("ac-save").onclick = () => withBusy($("ac-save"), async () => {
  try {
    await postJSON("/api/actions", {
      enabled: $("ac-enabled").checked,
      calendar_name: $("ac-cal").value.trim(),
      email_enabled: $("ac-email").checked,
      mail_account: $("ac-mail-acct").value.trim(),
      media_enabled: $("ac-media").checked,
      search_enabled: $("ac-search").checked,
    });
    const tav = $("key-tavily").value.trim();
    if (tav) { await postJSON("/api/llm-keys", {tavily: tav}); loadLlmKeys(); }   // 金鑰與開關同卡，一起存
    flash($("ac-msg"), "已儲存（重啟 bot 生效）");
  } catch (e) { warn($("ac-msg"), "儲存失敗，請重試"); }
});

// allowlist（id + 別名）
async function loadAllow() {
  const d = await getJSON("/api/allowlist");
  const entries = d.entries || [];
  $("allowlist").innerHTML = "";
  entries.forEach((e, i) => {
    const li = document.createElement("li"); li.className = "chip";
    const wrap = document.createElement("div"); wrap.className = "chip-row";
    const alias = document.createElement("input"); alias.className = "alias-in"; alias.value = e.alias || ""; alias.placeholder = "別名";
    alias.onchange = async () => { entries[i].alias = alias.value; await postJSON("/api/allowlist", {entries}); };
    const idspan = document.createElement("span"); idspan.className = "mono id-tag"; idspan.textContent = e.id;
    wrap.appendChild(alias); wrap.appendChild(idspan); li.appendChild(wrap);
    const del = document.createElement("button"); del.className = "icon-btn"; del.title = "移除"; del.setAttribute("aria-label", "移除 " + e.id);
    del.innerHTML = '<svg class="ic"><use href="#i-trash"></use></svg>';
    del.onclick = async () => {
      if (!confirm("將「" + (e.alias || e.id) + "」移出白名單？bot 將不再回應此人")) return;
      const left = entries.filter(x => x.id !== e.id);
      try { await postJSON("/api/allowlist", {entries: left}); loadAllow(); refreshStatus(); }
      catch (err) { warn($("allow-msg"), "移除失敗"); }
    };
    li.appendChild(del); $("allowlist").appendChild(li);
  });
}
$("allow-add").onclick = async () => {
  const id = $("allow-new-id").value.trim();
  if (!/^\d{5,15}$/.test(id)) { warn($("allow-msg"), "user_id 需為 5–15 位數字"); return; }
  const d = await getJSON("/api/allowlist"); const entries = d.entries || [];
  if (entries.some(e => String(e.id) === id)) { warn($("allow-msg"), "已在名單中"); return; }
  let alias = $("allow-new-alias").value.trim();
  // 盡力驗證（查得到帶名字；查不到也照樣可加，因為常是預先加入還沒互動的同事）
  const v = await getJSON("/api/verify-tg-id?id=" + id).catch(() => ({ ok: false, reason: "error" }));
  let note;
  if (v.ok) { if (!alias) alias = v.name; note = "✓ 已驗證：" + v.name; }
  else if (v.reason === "no_token") note = "（未設 Bot Token，未驗證）";
  else if (v.reason === "bad_token") note = "（Bot Token 無效，未驗證）";
  else note = "（尚無法驗證，對方需先私訊過 bot）";
  entries.push({ id: Number(id), alias });
  await postJSON("/api/allowlist", { entries });
  $("allow-new-id").value = ""; $("allow-new-alias").value = ""; loadAllow(); refreshStatus();
  flash($("allow-msg"), "已加入 " + note);
};

// data sources (vault path + repos)
async function loadSources() {
  const s = await getJSON("/api/sources");
  $("src-obsidian").value = s.obsidian_path || "";
  $("src-repos").value = (s.github_repos || []).join("\n");
  $("src-code").value = s.code_root || "";
}
$("src-browse").onclick = async () => {
  try {
    const r = await postJSON("/api/pick-folder", {start: $("src-obsidian").value.trim()});
    if (r.path) { $("src-obsidian").value = r.path; flash($("bf-msg"), "已選擇路徑，按「重建索引 Obsidian」套用"); }
    else if (r.error) warn($("bf-msg"), "此視窗不支援原生選擇（瀏覽器模式），請手動貼路徑");
  } catch (e) { warn($("bf-msg"), "選擇資料夾失敗"); }
};
$("src-code-browse").onclick = async () => {
  try {
    const r = await postJSON("/api/pick-folder", {start: $("src-code").value.trim()});
    if (r.path) { $("src-code").value = r.path; flash($("src-code-msg"), "已選擇路徑，按下方「儲存」套用"); }
    else if (r.error) warn($("src-code-msg"), "此視窗不支援原生選擇（瀏覽器模式），請手動貼路徑");
  } catch (e) { warn($("src-code-msg"), "選擇資料夾失敗"); }
};

async function saveSources() {
  const repos = $("src-repos").value.split("\n").map(x => x.trim()).filter(Boolean);
  await postJSON("/api/sources", {obsidian_path: $("src-obsidian").value.trim(), github_repos: repos,
    code_root: $("src-code").value.trim()});
}

// 程式委派來源：只存路徑（委派讀活的 repo，不需重灌）
$("src-code-save").onclick = () => withBusy($("src-code-save"), async () => {
  $("src-code-msg").classList.remove("warn", "ok"); $("src-code-msg").textContent = "儲存中…";
  try { await saveSources(); flash($("src-code-msg"), "程式碼母資料夾已儲存（重啟 bot 生效）"); }
  catch (e) { warn($("src-code-msg"), "儲存失敗，請重試"); }
});

// 記憶：儲存並重建索引（按下自動先存來源、再灌入知識庫）— busy 鎖鈕、完成/失敗有明確訊息
const _bfBtns = [...document.querySelectorAll("[data-bf]")];
_bfBtns.forEach(b => b.onclick = () => withBusy(b, async () => {
  const src = b.dataset.bf, others = _bfBtns.filter(x => x !== b);
  others.forEach(x => x.disabled = true);
  $("bf-msg").classList.remove("warn", "ok"); $("bf-msg").textContent = "儲存來源中…";
  try {
    await saveSources();
    $("bf-msg").textContent = src + " 重建索引中…（需時，請稍候）";
    await postJSON("/api/backfill/" + src);
    flash($("bf-msg"), src + " 重建索引完成");
  } catch (e) { warn($("bf-msg"), src + " 重建索引失敗，請重試"); }
  finally { others.forEach(x => x.disabled = false); }
}));

// models
function _showThreshold() { $("md-threshold-val").textContent = (+$("md-threshold").value || 0).toFixed(2); }
$("md-threshold").oninput = _showThreshold;

async function loadModels() {
  const m = await getJSON("/api/models");
  $("md-general").value = m.general; $("md-code").value = m.code;
  $("md-threshold").value = m.threshold; _showThreshold();
  $("md-baseurl").value = m.openai_base_url || "";
}
// 本地模型下拉（自繪，避免 pywebview/WebKit 原生 <datalist> 定位 bug）
let _ollamaModels = [];

function _attachModelPicker(input) {
  const field = input.closest(".field");
  const menu = document.createElement("div");
  menu.className = "model-menu"; menu.hidden = true;
  field.appendChild(menu);
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const items = _ollamaModels.filter(m => m.toLowerCase().includes(q));
    menu.innerHTML = "";
    if (!items.length) { menu.hidden = true; return; }
    items.forEach(m => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "model-opt"; b.textContent = m;
      b.onmousedown = (e) => { e.preventDefault(); input.value = m; menu.hidden = true; };
      menu.appendChild(b);
    });
    menu.hidden = false;
  };
  input.addEventListener("focus", render);
  input.addEventListener("input", render);
  input.addEventListener("blur", () => setTimeout(() => { menu.hidden = true; }, 150));
}
_attachModelPicker($("md-general"));
_attachModelPicker($("md-code"));

async function loadOllamaModels() {
  const hint = $("md-models-hint");
  hint.textContent = "讀取本地模型…";
  try {
    const base = ($("md-baseurl").value || "").trim();   // 用欄位當下的值（免先儲存）
    const d = await getJSON("/api/llm-models" + (base ? "?base=" + encodeURIComponent(base) : ""));
    _ollamaModels = d.models || [];
    if (!d.endpoint) hint.textContent = "（未設相容端點；可直接輸入雲端模型名）";
    else if (d.error === "blocked") hint.textContent = "⚠️ 預覽僅放行本機/區網端點。第三方公開端點請填好後按「儲存」再撈。";
    else if (d.error || !_ollamaModels.length) hint.textContent = "⚠️ 端點連不到或無模型：" + d.endpoint;
    else hint.textContent = `本地端點 ${_ollamaModels.length} 個模型可選（點欄位選）`;
  } catch (e) { hint.textContent = "讀取失敗"; }
}
$("md-refresh-models").onclick = loadOllamaModels;
$("md-baseurl").addEventListener("change", loadOllamaModels);   // 打完 URL 失焦即自動撈（免儲存）

async function loadLlmKeys() {
  const k = await getJSON("/api/llm-keys");
  for (const name of ["gemini", "anthropic", "openai", "tavily"]) {
    const el = $("key-" + name);
    el.value = "";
    el.placeholder = k[name] ? "已設定 ••••••••" : "未設定";
  }
}
$("md-save").onclick = () => withBusy($("md-save"), async () => {
  try {
    await postJSON("/api/models", {general: $("md-general").value, code: $("md-code").value, threshold: $("md-threshold").value, openai_base_url: $("md-baseurl").value.trim()});
    const keys = {};
    for (const name of ["gemini", "anthropic", "openai"]) {
      const v = $("key-" + name).value.trim();
      if (v) keys[name] = v;          // 留空＝不變更
    }
    if (Object.keys(keys).length) await postJSON("/api/llm-keys", keys);
    flash($("md-msg"), "已儲存（重啟 bot 生效）");
    loadLlmKeys();
    loadOllamaModels();          // 端點可能改了，重撈本地模型清單
  } catch (e) { warn($("md-msg"), "儲存失敗，請重試"); }
});

// analysis (panel-direct query)
$("an-run").onclick = () => withBusy($("an-run"), async () => {
  const q = $("an-q").value.trim(); if (!q) return;
  $("an-msg").classList.remove("warn", "ok"); $("an-msg").textContent = "分析中…（綜合，約數十秒）";
  $("an-answer").textContent = ""; $("an-sources").textContent = "";
  try {
    const r = await postJSON("/api/analyze", {query: q});
    $("an-msg").textContent = "";
    $("an-answer").textContent = r.answer || "";
    $("an-sources").textContent = (r.sources || []).length ? "依據：" + r.sources.join("｜") : "";
  } catch (e) { warn($("an-msg"), "分析失敗，請重試"); }
});

// 瀏覽白名單
let _browseDomains = [];

function renderBrowse() {
  const ul = $("browse-list");
  ul.innerHTML = "";
  _browseDomains.forEach((d, i) => {
    const li = document.createElement("li");
    li.className = "chip";
    li.textContent = d;
    const x = document.createElement("button");
    x.type = "button"; x.className = "chip-x"; x.textContent = "×";
    x.onclick = () => { _browseDomains.splice(i, 1); renderBrowse(); };
    li.appendChild(x);
    ul.appendChild(li);
  });
}

async function loadBrowse() {
  try {
    const r = await getJSON("/api/browse/allowlist");
    _browseDomains = r.domains || [];
    renderBrowse();
    const e = await getJSON("/api/browse/enabled");
    $("browse-enabled").checked = !!e.enabled;
  } catch (e) { warn($("browse-msg"), "載入失敗"); }
}

function wireBrowse() {
  $("browse-enabled").addEventListener("change", async () => {
    const on = $("browse-enabled").checked;
    try {
      const r = await postJSON("/api/browse/enabled", { enabled: on });
      if (on) {
        flash($("browse-msg"), r.browser_ready
          ? "已啟用，專用 Chrome 已開啟 — 第一次請在該視窗登入要用的網站；重啟 bot 後生效"
          : "已啟用，但專用 Chrome 沒起來（請確認有裝 Google Chrome）；重啟 bot 後生效");
      } else {
        flash($("browse-msg"), "已停用，並關閉專用 Chrome；重啟 bot 後生效");
      }
    } catch (e) {
      $("browse-enabled").checked = !on;   // 失敗回復
      warn($("browse-msg"), "切換失敗，請重試");
    }
  });
  $("browse-add").addEventListener("click", () => {
    const v = $("browse-input").value.trim().toLowerCase();
    if (v && !_browseDomains.includes(v)) { _browseDomains.push(v); renderBrowse(); }
    $("browse-input").value = "";
  });
  $("browse-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("browse-add").click();
  });
  $("browse-save").addEventListener("click", () => withBusy($("browse-save"), async () => {
    try {
      await postJSON("/api/browse/allowlist", { domains: _browseDomains });
      flash($("browse-msg"), "已儲存，重啟 bot 後生效");
    } catch (e) { warn($("browse-msg"), "儲存失敗，請重試"); }
  }));
}

loadProfile(); loadLeave(); loadBotToken(); loadAllow(); loadModels(); loadLlmKeys(); loadOllamaModels(); loadSources(); loadActions(); loadLibre(); loadMemPersons(); loadBrowse(); wireBrowse(); refreshStatus(); refreshLog();
setInterval(refreshStatus, 5000);
setInterval(refreshLog, 4000);

// 助理對 owner 的長期認識（自動畫像）：唯讀檢視 + 清除
// 註：函式名不可叫 loadProfile —— 會蓋掉上面載入「身份設定」的同名函式（/api/profile）。
async function loadLearnedProfile() {
  try {
    const r = await fetch("/api/memory/profile");
    const d = await r.json();
    document.getElementById("mem-profile").textContent = (d.profile || "").trim() || "—";
  } catch (e) { /* 面板非關鍵，靜默 */ }
}
document.getElementById("mem-profile-clear")?.addEventListener("click", async () => {
  if (!confirm("確定清除助理對你的長期認識？")) return;
  await fetch("/api/memory/profile/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  document.getElementById("mem-profile-msg").textContent = "已清除";
  loadLearnedProfile();
});
loadLearnedProfile();

// info「i」提示框：打開時夾進可視範圍，靠右緣就改往左展開，避免被視窗裁切（與卡片位置無關）
function _clampInfoTip(tip) {
  const box = tip.querySelector(".info-text");
  if (!box) return;
  box.style.left = "-8px"; box.style.right = "auto";          // 先回預設（往右展開）
  const pad = 10, vw = document.documentElement.clientWidth;
  let r = box.getBoundingClientRect();
  if (r.right > vw - pad) {                                   // 右溢出 → 改靠右、往左展開
    box.style.left = "auto"; box.style.right = "-8px";
    r = box.getBoundingClientRect();
    if (r.left < pad) {                                       // 改後又左溢出 → 平移夾住
      box.style.right = "auto";
      box.style.left = (pad - tip.getBoundingClientRect().left) + "px";
    }
  } else if (r.left < pad) {                                  // 左溢出 → 平移夾住
    box.style.left = (pad - tip.getBoundingClientRect().left) + "px";
  }
}
document.querySelectorAll(".info-tip").forEach(t => {
  t.addEventListener("mouseenter", () => _clampInfoTip(t));
  t.addEventListener("focusin", () => _clampInfoTip(t));
});
