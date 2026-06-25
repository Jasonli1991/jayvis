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
    '<button class="r-del" type="button" title="移除"><svg class="ic"><use href="#i-trash"></use></svg></button>';
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
      owner_name: name, title, company, assistant_name: (name || "") + " 的搭檔",
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

// logo 狀態：面板開場先醒著 ~3.5 秒（打招呼），之後依 bot 是否運作切「醒 / 睡(😴)」
const _brandLogo = document.querySelector("svg.brand-logo");
// 測試/開發：?stage=baby|normal|scholar 強制 logo 成長階段（無此參數＝依真實資料判定）。
const _forceStage = (() => {
  const s = new URLSearchParams(location.search).get("stage");
  return ["baby", "normal", "scholar"].includes(s) ? s : null;
})();
// 重建索引／認識自己的訊息該寫到哪個元素：含「認識自己」→ #selfdoc-msg（在按鈕下方）、其餘 → #bf-msg。
// 用訊息內容判斷（而非狀態變數）→ 連重新整理後輪詢沿用伺服器上次結果也會放對位置。
function _bfMsgFor(text) { return (text && text.indexOf("認識自己") >= 0) ? $("selfdoc-msg") : $("bf-msg"); }
let _logoIntro = true;          // true＝開場期間，輪詢不可動臉
let _restartTookOver = false;   // 重啟時設 true，讓開場收手
let _opBusy = false;            // 啟動/停止/重啟進行中：輪詢別動臉，讓「進行中」動畫獨佔到操作完成
const _reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion:reduce)").matches;

function _wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// 醒/睡切換：純切 .asleep class，過場交給 CSS 的 opacity 交叉淡入（兩張臉同位淡入淡出）。冪等、開場與 5 秒輪詢共用。
function swapFace(toAsleep) {
  if (!_brandLogo) return;
  if (_brandLogo.classList.contains("restarting")) return;             // dizzy 擁有臉，別搶
  _brandLogo.classList.toggle("asleep", toAsleep);                     // 已是該狀態則不變、不會閃
}

// 點擊 logo → 害羞臉紅反應（呼應角色秘密：被誇會亮粉紅）~1.2s 後淡回。
// 開場/操作中/暈眩(重啟) 時不搶臉——維持原動畫（暈眩＝「進行中」，別被打斷）。
let _reactT = null;
if (_brandLogo) _brandLogo.addEventListener("click", () => {
  if (_logoIntro || _opBusy || _brandLogo.classList.contains("restarting")) return;
  _brandLogo.classList.add("reacting");
  try { _brandLogo.pauseAnimations(); } catch (e) {}      // 凍住「看左右」→ 害羞表情靜止不錯位
  clearTimeout(_reactT);
  _reactT = setTimeout(() => {
    _brandLogo.classList.remove("reacting");
    try { _brandLogo.unpauseAnimations(); } catch (e) {}
  }, 1200);
});

// 開場：登場淡入落下 → 打招呼（既有 SMIL 轉頭/眨眼）→（若 bot 停止）打哈欠微沉後柔順淡入 😴。
async function _playLogoIntro() {
  if (!_brandLogo) { _logoIntro = false; return; }
  requestAnimationFrame(() => requestAnimationFrame(() => _brandLogo.classList.remove("logo-arming")));  // 首幀畫預備姿勢，下一幀才落下
  let s; try { s = await getJSON("/api/status"); } catch (e) { s = { running: true }; }
  if (_reduce) { _brandLogo.classList.toggle("asleep", !s.running); _logoIntro = false; refreshStatus(); return; }
  await _wait(6500);                                            // 落下＋打招呼：停留久一點，看得到轉頭幾次才想睡（原本 2s 太快）
  if (_restartTookOver) { _logoIntro = false; return; }         // 重啟中途接管 → 收手
  if (!s.running) {
    _brandLogo.classList.add("yawning"); await _wait(450);      // 打哈欠微沉
    _brandLogo.classList.add("asleep");                         // 柔順交叉淡入 → 😴（CSS .7s）
    await _wait(900);
    _brandLogo.classList.remove("yawning");
  }
  _logoIntro = false;
  refreshStatus();                                              // 對帳徽章/按鈕（臉已正確）
}
_playLogoIntro();

async function refreshStatus() {
  const s = await getJSON("/api/status");
  // 操作進行中（_opBusy）：狀態列文字／燈號／按鈕／臉一律交給按鈕 handler，輪詢別插手——
  // 否則 5 秒輪詢會在「停止中…」途中讀到 running=true，把文字洗成「運行中」，等真的關掉才變「已停止」。
  if (!_opBusy) {
    $("dot").className = "dot " + (s.running ? "on" : "off");
    $("botstate").textContent = s.running ? "運行中" : "已停止";
    if (_brandLogo && !_logoIntro && !_brandLogo.classList.contains("restarting")) swapFace(!s.running);   // 醒/睡(😴) 隨 bot 狀態：交叉淡入、冪等不閃
    // 運行中 → 停用「啟動」；停止 → 停用「停止/重啟」
    document.querySelectorAll(".botbtns button").forEach(x => { x.disabled = x.dataset.act === "start" ? s.running : !s.running; });
  }
  $("models").textContent = (s.models.general || "?").split("-").pop() + " / " + (s.models.code || "?").split("-").pop();
  const _memLabel = {conversation: "對話索引", action: "動作", git: "git", obsidian: "obsidian", manual: "自我說明"};
  $("mem").textContent = Object.entries(s.memory || {}).map(([k, v]) => `${_memLabel[k] || k} ${v}`).join("、") || "—";
  const _seeded = (s.memory && s.memory.manual) > 0;       // 自我說明是否已灌進 KB → 給初次使用者狀態提示
  const _sd = $("selfdoc-status");
  if (_sd) { _sd.textContent = _seeded ? "✅ 已認識自己" : "⚠️ 尚未認識自己"; _sd.classList.toggle("ok", _seeded); _sd.classList.toggle("warn", !_seeded); }
  // logo 成長階段彩蛋：未認識自己=嬰兒 👶、認識後=一般 🤖、owner 對談≥100 則=學士 🎓
  if (_brandLogo) {
    const stage = _forceStage || (!_seeded ? "baby" : (s.owner_graduated ? "scholar" : "normal"));   // 學士＝持久化畢業里程碑；?stage= 可強制（測試用）
    _brandLogo.classList.toggle("stage-baby", stage === "baby");
    _brandLogo.classList.toggle("stage-normal", stage === "normal");
    _brandLogo.classList.toggle("stage-scholar", stage === "scholar");
  }
  $("allowcount").textContent = s.allowlist;
  if (s.owner_name) {
    document.querySelector(".brand-name").textContent = s.owner_name + " 的個人 AI 搭檔";
  }
  if (s.version) $("ver").textContent = "v" + s.version;
  if (s.backfill && s.backfill.last) _bfMsgFor(s.backfill.last).textContent = s.backfill.last;
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
function showStartAlert(problems) {
  const el = $("start-alert");
  el.innerHTML = '<div class="sa-box"><div class="sa-head">⛔ 無法啟動，請先補上：</div><ul>'
    + problems.map(p => "<li>" + esc(p) + "</li>").join("") + "</ul></div>";
  el.hidden = false;
}
function hideStartAlert() { const el = $("start-alert"); if (el) { el.hidden = true; el.innerHTML = ""; } }

document.querySelectorAll(".botbtns button").forEach(b =>
  b.onclick = async () => {
    const act = b.dataset.act, btns = [...document.querySelectorAll(".botbtns button")];
    btns.forEach(x => x.disabled = true);
    const ic = b.querySelector(".ic"); if (ic) ic.classList.add("spin");
    $("botstate").textContent = {start: "啟動中…", stop: "停止中…", restart: "重啟中…"}[act] || "處理中…";
    _opBusy = true;                                 // 操作進行中：logo 動畫獨佔、輪詢不插手（直到 finally）
    if (_brandLogo) {                               // 進行中一律暈眩(😵‍💫)「處理中」：迴圈動畫自動撐滿任何時長，與狀態文字／轉圈同生命週期
      _restartTookOver = true;                      // 讓開場收手
      _brandLogo.classList.remove("asleep", "yawning");
      _brandLogo.classList.add("restarting");
    }
    try {
      const r = await postJSON("/api/bot/" + act);
      if (r && r.ok === false && r.problems && r.problems.length) {
        showStartAlert(r.problems);                 // pre-flight 擋下：列出缺什麼
        $("botstate").textContent = "未啟動：缺設定";
      } else {
        hideStartAlert();
      }
      if (_brandLogo) _brandLogo.classList.toggle("asleep", !(r && r.running));   // 在暈眩底下先設好最終臉，撤暈眩時直接露出、不閃中間態
    }
    catch (e) { $("botstate").textContent = "操作失敗，請看 Log"; }
    finally {
      if (ic) ic.classList.remove("spin");          // 轉圈、暈眩、狀態文字 三者同時結束＝時間一致
      if (_brandLogo) { _brandLogo.classList.remove("restarting"); _restartTookOver = false; }   // 撤暈眩 → 交叉淡入到已設好的 醒/睡臉
      _opBusy = false;
      await refreshStatus();                        // 對帳徽章/按鈕（臉已正確）
    }
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

function _focusLeaveHint() {
  // 本週重點文字提到請假、卻沒設日期區間 → 提醒：系統只認日期，不會從文字判定請假
  const hasDates = !!(calState.start && calState.end);
  if (/請假|休假|特休|年假/.test($("lv-focus").value) && !hasDates) {
    warn($("lv-msg"), "提醒：本週重點提到請假，但沒設請假期間。請用上方日期選擇器設定，系統才會真的當你請假（觸發代理／彙整）。");
  }
}

async function loadLeave() {
  const d = await getJSON("/api/leave");
  $("lv-status").value = d.status || ""; $("lv-focus").value = d.focus || "";
  calState.start = _parseISO(d.leave_start); calState.end = _parseISO(d.leave_end); _renderRangeText();
  _focusLeaveHint();
}
$("lv-focus").addEventListener("blur", _focusLeaveHint);
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

$("lv-digest").onclick = () => withBusy($("lv-digest"), async () => {
  $("lv-digest-msg").classList.remove("warn", "ok");
  $("lv-digest-msg").textContent = "彙整中…（讀請假期間同事對話，可能數十秒）";
  $("lv-digest-out").textContent = "";
  try {
    const r = await postJSON("/api/leave/digest", {});
    if (r.ok) {
      $("lv-digest-out").textContent = r.summary || "";
      $("lv-digest-msg").classList.add("ok");
      $("lv-digest-msg").textContent = "已彙整" + (r.tg_sent ? "，已發到 TG" : "");
    } else { warn($("lv-digest-msg"), r.error || "彙整失敗，請重試"); }
  } catch (e) { warn($("lv-digest-msg"), "彙整失敗，請重試"); }
});

$("lv-focus-draft").onclick = () => withBusy($("lv-focus-draft"), async () => {
  $("lv-focus-draft-msg").classList.remove("warn", "ok");
  $("lv-focus-draft-msg").textContent = "擬稿中…（讀近期對話/筆記，可能數十秒）";
  try {
    const r = await postJSON("/api/leave/focus-draft", {brief: $("lv-focus-brief").value.trim()});
    if (r.ok) {
      if (!$("lv-focus").value.trim() || confirm("本週重點已有內容，要用 AI 草稿覆蓋嗎？")) {
        $("lv-focus").value = r.draft || "";
        _focusLeaveHint();
        $("lv-focus-draft-msg").classList.add("ok");
        $("lv-focus-draft-msg").textContent = "已產生草稿，請編修後按「儲存請假設定」";
      } else { $("lv-focus-draft-msg").textContent = "已取消覆蓋"; }
    } else { warn($("lv-focus-draft-msg"), r.error || "擬稿失敗，請重試"); }
  } catch (e) { warn($("lv-focus-draft-msg"), "擬稿失敗，請重試"); }
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
  $("ig-enabled").checked = (await getJSON("/api/image-gen/enabled")).enabled;
}

function wireImageGen() {
  $("ig-enabled").addEventListener("change", async () => {
    try {
      await postJSON("/api/image-gen/enabled", { enabled: $("ig-enabled").checked });
      flash($("ac-msg"), "已更新，重啟 bot 後生效");
    } catch (e) {
      $("ig-enabled").checked = !$("ig-enabled").checked;
      warn($("ac-msg"), "切換失敗，請重試");
    }
  });
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
  const box = $("mem-timeline");
  if (!pid) { box.innerHTML = ""; return; }
  const tl = await getJSON("/api/memory/timeline?person=" + encodeURIComponent(pid));
  const html = tl.map(m =>
    `<li><span class="hint">${esc(m.ts)}・${esc(m.kind)}</span><br>${esc(m.content)}</li>`).join("") || "<li class='hint'>（無記錄）</li>";
  if (box.innerHTML === html) return;                                  // 沒變就不動（免閃爍、不跳捲動）
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 4;
  const prevTop = box.scrollTop;
  box.innerHTML = html;
  box.scrollTop = atBottom ? box.scrollHeight : prevTop;               // 原在底部→跟到最新，否則保留位置
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
// 聊天記憶 匯出（原生另存）
$("mem-export").onclick = () => withBusy($("mem-export"), async () => {
  const m = $("mem-iexp-msg");
  let r; try { r = await postJSON("/api/memory/export", {}); } catch (e) { warn(m, "匯出失敗"); return; }
  if (r.ok) flash(m, `已匯出 ${r.count} 則 → ${r.path}`); else warn(m, r.error || "匯出失敗");
});
// 聊天記憶 匯入（原生選 .json → 背景灌入 → 輪詢進度）
$("mem-import").onclick = () => withBusy($("mem-import"), async () => {
  const m = $("mem-iexp-msg");
  let pick; try { pick = await postJSON("/api/memory/import-pick", {}); } catch (e) { warn(m, "無法開啟選檔視窗"); return; }
  if (!pick.path) { m.textContent = ""; return; }                       // 取消
  if ($("mem-import-clear").checked && !confirm("會先清空你（owner）現有的對談記憶再匯入，確定？")) return;
  let r; try { r = await postJSON("/api/memory/import", {path: pick.path, clearFirst: $("mem-import-clear").checked, rebuild: $("mem-import-rebuild").checked}); }
  catch (e) { warn(m, "匯入失敗"); return; }
  if (!r.ok) { warn(m, r.error || "匯入失敗"); return; }
  m.classList.remove("warn", "ok"); m.textContent = `開始匯入 ${r.count} 則…（embedding 較慢，請稍候）`;
  const poll = setInterval(async () => {                                // 輪詢背景進度
    let s; try { s = await getJSON("/api/memory/import-status"); } catch (e) { return; }
    m.textContent = s.last || "";
    if (!s.running) { clearInterval(poll); loadMemPersons(); loadLearnedProfile(); refreshStatus(); }
  }, 1000);
});
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
// 注意：/api/backfill 非阻塞（開背景 thread 就回），所以要輪詢到背景真的跑完才算完成
async function waitBackfill(maxMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    await new Promise(r => setTimeout(r, 1000));
    try {
      const s = await getJSON("/api/status");
      if (s.backfill) {
        if (s.backfill.last) _bfMsgFor(s.backfill.last).textContent = s.backfill.last;   // 顯示「執行中…」進度
        if (!s.backfill.running) return s.backfill.last || "";            // 真的跑完才回
      }
    } catch (e) {}
  }
  return "";
}

const _bfLabel = { obsidian: "Obsidian", github: "GitHub", self: "JAYVIS 自我說明" };
const _bfBtns = [...document.querySelectorAll("[data-bf]")];
_bfBtns.forEach(b => b.onclick = () => withBusy(b, async () => {
  const src = b.dataset.bf, others = _bfBtns.filter(x => x !== b), label = _bfLabel[src] || src;
  const msg = (src === "self") ? $("selfdoc-msg") : $("bf-msg");   // self 的訊息顯示在「認識自己」按鈕下方
  others.forEach(x => x.disabled = true);
  msg.classList.remove("warn", "ok");
  try {
    if (src === "self") {                              // 自我說明：與 Obsidian/GitHub 來源無關，免存來源
      msg.textContent = "讓 JAYVIS 認識自己中…（首次需下載本地模型，請稍候）";
    } else {
      msg.textContent = "儲存來源中…";
      await saveSources();
      msg.textContent = label + " 重建索引中…（需時，請稍候）";
    }
    await postJSON("/api/backfill/" + src);
    const last = await waitBackfill(180000);          // 等背景索引真的完成再報結果
    const txt = last || (label + " 完成");
    if (/^⚠️/.test(txt)) warn(msg, txt); else flash(msg, txt);   // ⚠️ 開頭＝有狀況（如 gh 未登入），用警示樣式
  } catch (e) { warn(msg, label + " 失敗，請重試"); }
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
  loadProviderModels();
}
// 模型下拉（自繪，避免 pywebview/WebKit 原生 <datalist> 定位 bug）
let _ollamaModels = [];
let _cloudModels = [];   // 三家雲端（Google/Anthropic/OpenAI）對話模型

function _attachModelPicker(input) {
  const field = input.closest(".field");
  const menu = document.createElement("div");
  menu.className = "model-menu"; menu.hidden = true;
  field.appendChild(menu);
  const render = () => {
    const q = input.value.trim().toLowerCase();
    const items = [...new Set([..._cloudModels, ..._ollamaModels])].filter(m => m.toLowerCase().includes(q));
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
async function loadProviderModels() {
  try {
    const d = await getJSON("/api/provider-models");
    _cloudModels = d.models || [];
  } catch (e) { _cloudModels = []; }
}
$("md-refresh-models").onclick = () => { loadProviderModels(); loadOllamaModels(); };
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
  $("an-msg").classList.remove("warn", "ok"); $("an-msg").textContent = "分析中…（產生報告，可能 1–2 分鐘）";
  try {
    const r = await postJSON("/api/analyze", {query: q});
    if (r.ok) { $("an-msg").classList.add("ok"); $("an-msg").textContent = "已產生報告並開啟：" + (r.filename || ""); }
    else { warn($("an-msg"), r.error || "分析失敗，請重試"); }
  } catch (e) { warn($("an-msg"), "分析失敗，請重試"); }
});

$("an-refine-run").onclick = () => withBusy($("an-refine-run"), async () => {
  const ins = $("an-refine").value.trim(); if (!ins) return;
  $("an-refine-msg").classList.remove("warn", "ok");
  $("an-refine-msg").textContent = "修改中…（重生報告，可能 1–2 分鐘）";
  try {
    const r = await postJSON("/api/analyze/refine", {instruction: ins});
    if (r.ok) { $("an-refine-msg").classList.add("ok"); $("an-refine-msg").textContent = "已產生新版並開啟：" + (r.filename || ""); }
    else { warn($("an-refine-msg"), r.error || "修改失敗，請重試"); }
  } catch (e) { warn($("an-refine-msg"), "修改失敗，請重試"); }
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
    x.type = "button"; x.className = "r-del"; x.title = "移除"; x.innerHTML = '<svg class="ic"><use href="#i-trash"></use></svg>';
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
    refreshLoginBtn();
  } catch (e) { warn($("browse-msg"), "載入失敗"); }
}

function _sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function waitBrowseReady(maxMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    const s = await getJSON("/api/browse/ready");
    if (s.ready) return true;
    if (!s.installing) return false;          // 沒在裝又沒好 → 視為失敗
    flash($("browse-msg"), "正在背景下載瀏覽器元件…（約 1–2 分鐘，可繼續用面板）");
    await _sleep(4000);
  }
  return false;
}

async function refreshLoginBtn() {
  try {
    const s = await getJSON("/api/browse/login/status");
    const inLogin = !!s.login_mode;
    $("browse-login-btn").textContent = inLogin ? "完成登入" : "開啟登入視窗";
    $("browse-login-status").textContent = inLogin
      ? "登入中：已開啟視窗，登好你要的網站後按「完成登入」回背景模式" : "";
  } catch (e) {}
}

$("browse-login-btn").onclick = async () => {
  const inLogin = $("browse-login-btn").textContent === "完成登入";
  try {
    await postJSON(inLogin ? "/api/browse/login/end" : "/api/browse/login/begin", {});
  } catch (e) {}
  refreshLoginBtn();
};

function wireBrowse() {
  $("browse-enabled").addEventListener("change", async () => {
    const on = $("browse-enabled").checked;
    try {
      if (on) {
        let st = await getJSON("/api/browse/ready");
        if (!st.ready) {                                    // 第一次：先提示、確定後才背景下載
          if (!st.installing) {
            if (!confirm("第一次啟用需下載瀏覽器元件（約 150MB）才能瀏覽。要現在安裝嗎？")) {
              $("browse-enabled").checked = false;
              flash($("browse-msg"), "已取消安裝");
              return;
            }
            await postJSON("/api/browse/install", {});      // 背景啟動，不阻塞
          }
          const okReady = await waitBrowseReady(300000);    // 輪詢最多 5 分鐘
          if (!okReady) {
            $("browse-enabled").checked = false;
            warn($("browse-msg"), "安裝未完成，請看終端 Log 後再試");
            return;
          }
        }
        const res = await postJSON("/api/browse/enabled", { enabled: true });
        flash($("browse-msg"), res.browser_ready
          ? "已啟用，專用瀏覽器已開啟 — 第一次請在該視窗登入要用的網站；重啟 bot 後生效"
          : "已啟用，但瀏覽器沒起來，請看 Log；重啟 bot 後生效");
      } else {
        await postJSON("/api/browse/enabled", { enabled: false });
        flash($("browse-msg"), "已停用，並關閉專用瀏覽器；重啟 bot 後生效");
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

// GitHub repos picker：gh 登入後從帳號帶入 repo（點選加入欄位、自動去重）
(function () {
  const btn = $("src-repos-pick"), menu = $("src-repos-menu"), msg = $("src-repos-msg"), ta = $("src-repos");
  if (!btn) return;
  const curRepos = () => ta.value.split("\n").map(x => x.trim()).filter(Boolean);
  btn.onclick = async () => {
    msg.classList.remove("warn", "ok"); msg.textContent = "讀取中…";
    let r;
    try { r = await getJSON("/api/github/available-repos"); }
    catch (e) { warn(msg, "讀取失敗"); menu.hidden = true; return; }
    if (!r.ok) { warn(msg, r.error || "無法取得 repo 清單"); menu.hidden = true; return; }   // gh 未登入等
    if (!r.repos || !r.repos.length) { warn(msg, "找不到任何 repo"); menu.hidden = true; return; }
    msg.textContent = "";
    const have = new Set(curRepos());
    menu.innerHTML = "";
    r.repos.forEach(repo => {
      const o = document.createElement("button");
      o.type = "button"; o.className = "model-opt";
      o.textContent = have.has(repo) ? repo + "  ✓" : repo;
      o.onclick = () => {
        if (!curRepos().includes(repo)) ta.value = [...curRepos(), repo].join("\n");
        o.textContent = repo + "  ✓";
      };
      menu.appendChild(o);
    });
    menu.hidden = false;
  };
  document.addEventListener("pointerdown", (e) => {
    if (!menu.hidden && !menu.contains(e.target) && !btn.contains(e.target)) menu.hidden = true;
  });
})();

loadProfile(); loadLeave(); loadBotToken(); loadAllow(); loadModels(); loadLlmKeys(); loadOllamaModels(); loadSources(); loadActions(); loadLibre(); loadMemPersons(); loadBrowse(); wireBrowse(); wireImageGen(); refreshStatus(); refreshLog();
setInterval(refreshStatus, 5000);
setInterval(refreshLog, 4000);

// 搭檔對 owner 的長期認識（自動畫像）：唯讀檢視 + 清除
// 註：函式名不可叫 loadProfile —— 會蓋掉上面載入「身份設定」的同名函式（/api/profile）。
let _profileSig = null;                                      // 變了才重繪（免文字/頭像閃爍）
async function loadLearnedProfile() {
  try {
    const r = await fetch("/api/memory/profile");
    const d = await r.json();
    const prof = (d.profile || "").trim();
    const sig = prof + "" + JSON.stringify(d.portrait || null);
    if (sig === _profileSig) return;
    _profileSig = sig;
    document.getElementById("mem-profile").textContent = prof || "—";
    renderOwnerPortrait(d.portrait, prof);
  } catch (e) { /* 面板非關鍵，靜默 */ }
}

// JAYVIS 依「長期認識」觀察畫的 owner 塗鴉頭像（程式即時畫、零繪圖 token）。
// 種子＝畫像文字 → 同一份觀察每次都長一樣、觀察一更新就重畫；spec＝後端模型依觀察＋名字挑的特徵。
function renderOwnerPortrait(spec, profileText) {
  const fig = document.getElementById("mem-portrait");
  const svg = document.getElementById("mem-portrait-svg");
  if (!fig || !svg || typeof jayvisDoodle !== "function") return;
  if (!profileText) { fig.hidden = true; svg.innerHTML = ""; return; }   // 還沒認識你 → 不畫
  try {
    svg.innerHTML = jayvisDoodle(spec || {}, profileText);
    fig.hidden = false;
  } catch (e) { fig.hidden = true; }
}
document.getElementById("mem-profile-clear")?.addEventListener("click", async () => {
  if (!confirm("確定清除 JAYVIS 對你的長期認識？")) return;
  await fetch("/api/memory/profile/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  document.getElementById("mem-profile-msg").textContent = "已清除";
  loadLearnedProfile();
});
loadLearnedProfile();

// 對談記憶 / 長期認識：面板重新可見或取得焦點時自動刷新（切走再回來即更新，免重啟面板）；
// 開著時也緩速更新（只在可見時，比 status 的 5s 慢很多）。操作進行中或正在操作下拉時不打擾。
function _autoRefreshMemory() {
  if (_opBusy) return;                                       // 啟動/停止/重啟進行中 → 不打擾
  if (document.activeElement === $("mem-person")) return;    // 使用者正在操作下拉 → 不搶
  loadMemPersons().catch(() => {});                          // 內含 loadMemTimeline（保留捲動、變了才重繪）
  loadLearnedProfile();                                       // 變了才重繪
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") _autoRefreshMemory();
});
window.addEventListener("focus", _autoRefreshMemory);
setInterval(() => { if (document.visibilityState === "visible") _autoRefreshMemory(); }, 15000);

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

// 解除安裝：掃描→勾選（JAYVIS 裝的預設勾、來源不明的需自行勾）→輸入「移除」二次確認→執行（後端要求先停 bot）
(function () {
  const scanBtn = $("uninst-scan");
  if (!scanBtn) return;
  const body = $("uninst-body"), runBtn = $("uninst-run"),
        confirmTxt = $("uninst-confirm-txt"), result = $("uninst-result");
  const KIND = {model: "模型", chromium: "Chromium 瀏覽器", libreoffice: "LibreOffice"};

  function mkRow(it, checked) {                       // 用 DOM 建構（路徑當 textContent/dataset，免跳脫風險）
    const lab = document.createElement("label"); lab.className = "uninst-row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = checked; cb.dataset.path = it.path;
    const nm = document.createElement("span"); nm.className = "uninst-name";
    nm.textContent = (KIND[it.kind] || it.kind) + (it.name ? ` (${it.name})` : "");
    const sz = document.createElement("span"); sz.className = "uninst-size"; sz.textContent = it.size_h;
    const pa = document.createElement("span"); pa.className = "uninst-path"; pa.textContent = it.path;
    lab.append(cb, nm, sz, pa);
    cb.addEventListener("change", refreshRun);
    return lab;
  }
  function refreshRun() {
    const any = [...body.querySelectorAll("input[type=checkbox]")].some(c => c.checked);
    runBtn.disabled = !(any && confirmTxt.value.trim() === "移除JAYVIS");
  }
  async function scan() {
    scanBtn.disabled = true; scanBtn.textContent = "掃描中…";
    let s;
    try { s = await getJSON("/api/uninstall/scan"); }
    catch (e) { scanBtn.textContent = "掃描失敗，重試"; scanBtn.disabled = false; return; }
    scanBtn.textContent = "重新掃描"; scanBtn.disabled = false;
    const tc = $("uninst-tracked"); tc.innerHTML = "";
    (s.tracked || []).filter(it => it.exists).forEach(it => tc.append(mkRow(it, true)));
    $("uninst-tracked-wrap").hidden = tc.children.length === 0;
    const lc = $("uninst-legacy"); lc.innerHTML = "";
    (s.legacy || []).forEach(it => lc.append(mkRow(it, false)));
    $("uninst-legacy-wrap").hidden = (s.legacy || []).length === 0;
    $("uninst-data-size").textContent = s.data.size_h;
    $("uninst-data-wrap").hidden = s.data.count === 0;
    $("uninst-cleardata").addEventListener("change", refreshRun);
    body.hidden = false; refreshRun();
  }
  async function run() {
    const paths = [...body.querySelectorAll("#uninst-tracked input:checked, #uninst-legacy input:checked")].map(c => c.dataset.path);
    const clearData = $("uninst-cleardata").checked;
    if (!paths.length && !clearData) return;
    runBtn.disabled = true; runBtn.textContent = "移除中…";
    let r;
    try { r = await postJSON("/api/uninstall/remove", {paths, clearData}); }
    catch (e) { r = {ok: false, error: String(e)}; }
    runBtn.textContent = "執行移除所選";
    result.hidden = false;
    result.textContent = r.ok === false
      ? "⚠️ " + (r.error || "失敗")
      : ((r.results || []).map(x => (x.ok ? "✓ " : "✗ ") + x.path + " — " + x.msg).join("\n") || "（無項目）");
    confirmTxt.value = "";
    refreshStatus();
    const allOk = r.ok !== false && (r.results || []).length > 0 && (r.results || []).every(x => x.ok);
    if (allOk && $("uninst-close-after").checked) { startCountdown(); return; }   // 全部成功＋勾選 → 倒數關閉，不重掃
    setTimeout(scan, 400);                            // 否則重掃更新清單與容量
  }
  function startCountdown() {                         // 5 秒可取消倒數後關閉整個 JAYVIS
    const el = $("uninst-countdown"); el.hidden = false; el.innerHTML = "";
    const txt = document.createElement("span");
    const cancel = document.createElement("button"); cancel.className = "uninst-btn"; cancel.textContent = "取消";
    el.append(txt, cancel);
    let n = 5;
    const tick = () => { txt.textContent = `✅ 完成。JAYVIS 將在 ${n} 秒後關閉…　`; };
    tick();
    const id = setInterval(() => {
      n--;
      if (n <= 0) { clearInterval(id); txt.textContent = "關閉中…"; cancel.remove(); postJSON("/api/quit", {}).catch(() => {}); }
      else tick();
    }, 1000);
    cancel.onclick = () => { clearInterval(id); el.hidden = true; setTimeout(scan, 100); };
  }
  scanBtn.addEventListener("click", scan);
  confirmTxt.addEventListener("input", refreshRun);
  runBtn.addEventListener("click", run);
  $("uninst-cleardata").addEventListener("change", e => { if (e.target.checked) $("uninst-close-after").checked = true; });  // 清資料＝完整離場 → 順手預勾關閉（仍可取消勾選）
})();
