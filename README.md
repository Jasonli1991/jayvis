# JAYVIS

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB" />
  <img src="https://img.shields.io/badge/Telegram-Bot%20API-26A5E4" />
  <img src="https://img.shields.io/badge/SQLite-FTS5%20%2B%20numpy-003B57" />
  <img src="https://img.shields.io/badge/Flask%20%2B%20pywebview-控制台-000000" />
  <img src="https://img.shields.io/badge/LLM-Gemini%20%C2%B7%20Claude%20%C2%B7%20OpenAI%20%C2%B7%20Ollama-F3B54A" />
  <img src="https://img.shields.io/badge/license-MIT-success" />
</p>

> **JAYVIS** 是一個自架的個人 Telegram AI 助理。當你不在線（或請假）時，同事可以**私訊它**或在工作群組**「@ 它」**，它會用**自己的助理人設**（幽默、有台灣味、會表明「我是你的助理」、**不冒充你本人**）、根據**你自己的知識庫**（Obsidian 筆記、GitHub commits、Telegram 對話）誠實回答 —— 沒把握就老實說、不編造。附帶一個桌面**控制台**把所有設定點一點就好，**全部跑在本機**（單一檔 SQLite，不需要任何資料庫伺服器），也很容易換個人就變成「他的」助理。

---

## 目錄

- [這是什麼、適合誰](#這是什麼適合誰)
- [功能總覽](#功能總覽)
- [技術架構](#技術架構)
- [快速開始（手把手教學）](#快速開始手把手教學)
- [設定詳解](#設定詳解)
- [控制台逐卡說明](#控制台逐卡說明)
- [怎麼用：你本人 / 同事 / 群組](#怎麼用你本人--同事--群組)
- [私訊 vs 群組 功能對照表](#私訊-vs-群組-功能對照表)
- [運作原理](#運作原理)
- [請假、本週重點、請假彙整](#請假本週重點請假彙整)
- [資料儲存（`~/.n/`）](#資料儲存n)
- [專案結構](#專案結構)
- [換人使用（多租戶）](#換人使用多租戶)
- [常見問題 FAQ](#常見問題-faq)
- [測試](#測試)
- [授權](#授權)

---

## 這是什麼、適合誰

JAYVIS 是給「希望請假/離線時，同事仍能問到事情」的人用的個人助理：

- **你本人**私訊它 → 它是你的私人助理：查知識庫、查時事、生圖、改圖、管行事曆/信、看網頁、甚至把程式問題委派給 Coding Agent。
- **同事**（白名單內）私訊或在群組 @ 它 → 它用「**你的助理**」身分回答，只依知識庫、誠實、不冒充你本人、不亂掰你的私事。
- 全部**本機執行、long polling**，不需要公開網址、不需要 Postgres。

---

## 功能總覽

| 功能 | 說明 |
|------|------|
| **知識庫問答（RAG）** | 對 Obsidian＋GitHub commits＋Telegram 對話做混合檢索（dense 向量＋FTS5＋RRF 融合＋rerank）；信心不足時**誠實說資料不足**並附來源，而不是硬掰。 |
| **JAYVIS 自己的人設** | 它是**有鮮明個性的助理**（幽默風趣、台灣味、有人情味），會表明「我是你的助理」、**絕不冒充你本人**、不編造你的私事。 |
| **本人 / 同事 / 群組三種模式** | 本人＝坦白的私人助理；同事＝同上人設、只依知識庫誠實作答；群組＝被 @ 才回、帶群組脈絡。 |
| **請假自動回覆** | 依你設定的「請假日期區間」自動判定狀態，告訴同事你是否請假、何時回來。 |
| **LLM 代擬本週重點** | 面板一鍵，從近期對話／commits／近期筆記／一句方向，幫你擬一份「本週重點／交接重點」草稿，編修後再儲存。 |
| **請假期間彙整** | 把請假區間內同事與助理的對話整理成「已處理項目＋待辦」，面板顯示並發到你的 TG；請假結束自動 DM 你一次。 |
| **多供應商模型路由** | 依模型名稱前綴自動分流 **Gemini / Claude / OpenAI / 本地 Ollama**；面板金鑰一律遮罩。 |
| **時事搜尋（Tavily）** | 你本人問股價/天氣/新聞等時效性問題時，先搜尋再帶來源回答（owner 限定，可開放群組）。 |
| **生圖、媒體工具、網站瀏覽** | owner 限定：自動配圖（Pollinations.AI）、圖片去背/轉檔/調尺寸、借用 Chromium 看網頁並操作。 |
| **行事曆 / 收發信（macOS）** | owner 限定，預設關閉、寫入前先問你確認，透過 AppleScript 驅動 Calendar.app / Mail.app。 |
| **程式委派** | owner 限定：把本機專案的程式問題交給 headless Coding Agent 問答／擬修復計畫／改碼開 PR。 |
| **分析模式** | 面板（或私訊 `分析：…`）廣撈知識庫＋強模型，產出**自帶 Chart.js 的 HTML 報告**存進 Obsidian Inbox 並自動開啟，可「接續修改」出新版本。 |
| **控制台 App** | 原生視窗（亮/暗主題）管理身份、請假、白名單、模型、重建索引、動作工具、瀏覽、分析，並可啟動/停止/重啟 bot＋看即時 log。 |
| **本機優先、零伺服器** | 單一檔 SQLite 知識庫＋本地向量；不需要資料庫伺服器。 |

---

## 技術架構

| 層 | 技術 |
|----|------|
| **live 入口** | Python 3.11 · `python-telegram-bot` 21.9（Bot API，long polling） |
| **知識庫** | SQLite（FTS5）＋ numpy 餘弦相似度 ＋ Python RRF 融合（零伺服器） |
| **Embedding / rerank** | sentence-transformers（如 `BAAI/bge-m3`、`bge-reranker-v2-m3`） |
| **LLM 閘道** | google-genai（Gemini）· Anthropic · OpenAI · 本地 Ollama（OpenAI 相容）；依模型名前綴分流 |
| **控制台** | Flask（127.0.0.1:8765）＋ pywebview 原生視窗 |
| **知識來源** | Obsidian vault · GitHub commits · Telegram 對話 |
| **選用能力** | Tavily（時事）· Pollinations.AI（生圖）· Playwright Chromium（瀏覽）· rembg/Pillow（媒體）· AppleScript（行事曆/信，macOS） |

> 註：`python-telegram-bot` 的 JobQueue 需要 apscheduler（本專案未安裝），所有排程（如請假結束自動彙整）改用 **asyncio 背景任務**達成。

---

## 快速開始（手把手教學）

### 步驟 0｜先準備

- **Python 3.11**。
- 一支 **Telegram Bot**：在 Telegram 找 **@BotFather** → `/newbot` → 取得 **Bot Token**。
- 你的 **Telegram 數字 id**：找 **@userinfobot** 取得（這是 `OWNER_CHAT_ID`，決定誰是「你本人」）。
- 至少一個 **LLM 金鑰**（Gemini 有免費額度，最好上手），或一個本地 **Ollama**。

### 步驟 1｜安裝

```bash
git clone <your-fork-url> jayvis && cd jayvis
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 之後填金鑰（見「設定詳解」）
```

> 之後文件一律用 `.venv/bin/python` 代表虛擬環境的 Python（已 `source` 啟用後也可直接 `python`）。

### 步驟 2｜填設定（兩種方式擇一）

**方式 A（推薦）：開控制台用點的。**

```bash
.venv/bin/python -m panel
```

會開一個原生視窗（背後是 127.0.0.1:8765 的 Flask）。在裡面填「身份設定」「Telegram（Bot Token＋你的 id）」「模型（金鑰）」即可，存檔會寫進 gitignore 的本機檔。

**方式 B：直接編輯檔案。**

- `.env` —— 金鑰、id、模型、路徑（見下節變數表）。
- `prompts/owner_profile.json` —— 你的身份（名字、職稱、公司、專案、團隊、老闆、轉介規則）。範本：`prompts/owner_profile.example.json`。
- `prompts/WeeklyFocus.md` —— 本週重點＋請假日期。範本：`prompts/WeeklyFocus.example.md`。

> 這些個人檔**都不會進版控**；若不存在，JAYVIS 會自動退回 `.example` 範本，所以一裝好就能跑。

### 步驟 3｜建知識庫（選用，但建議）

```bash
.venv/bin/python backfill.py     # 首次會下載 embedding 模型，建立 ~/.n/kb.sqlite
```

或在控制台「重建索引」卡按一下（有即時進度 log）。沒設 Obsidian/GitHub 也能跑，只是沒有 RAG 來源。

### 步驟 4｜啟動

```bash
.venv/bin/python -m panel        # 推薦：用控制台設定 + 啟動/停止/重啟 bot
# 或
.venv/bin/python bot.py          # 直接跑 bot（long polling，不需公開網址）
```

控制台頂部有「啟動／停止／重啟」按鈕，改完設定按「重啟」即可生效。

### 步驟 5｜（要在群組用就做）關閉 Telegram 隱私模式

預設 BotFather 會開「群組隱私模式」，bot **收不到群組訊息**。要在群組用：

1. **@BotFather → `/setprivacy` → 選你的 bot → Disable**。
2. **把 bot 移出群組再重新加入**（此設定只對「之後加入的群組」生效，務必重加）。
3. 或者：直接把 bot **設成群組管理員**（管理員會繞過隱私模式）。

---

## 設定詳解

所有真正的設定都由 `.env`（或控制台寫入的本機檔）驅動，**個人資料一律不進版控**。`.env.example` 內有完整中文註解，這裡列重點：

| 變數 | 說明 | 預設 |
|------|------|------|
| `TG_BOT_TOKEN` | @BotFather 給的 Bot Token。 | （必填） |
| `OWNER_CHAT_ID` | 你的 TG 數字 id —— 唯一能觸發「本人模式」與動作工具的人。 | `0`（關） |
| `ALLOWLIST_USER_IDS` | 逗號分隔的同事 id；只有名單內＋你本人，bot 才回應。 | 空 |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | 模型金鑰，用到哪家填哪家。 | 空 |
| `OPENAI_BASE_URL` | OpenAI 相容端點（如本地 Ollama `http://localhost:11434/v1`）；設了之後，非 `gemini-*`/`claude-*`/`gpt-*` 的模型名都走這裡。 | 空 |
| `MODEL_GENERAL` / `MODEL_CODE` | 一般模型／高階模型名稱；**供應商由名稱前綴自動判定**。 | `gemini-2.5-flash` / `gemini-2.5-pro` |
| `RETRIEVAL_THRESHOLD` | 檢索信心門檻（低於就傾向誠實說資料不足）。 | `0.3` |
| `OBSIDIAN_PATH` | Obsidian vault 路徑（留空＝跳過 Obsidian）。 | 空 |
| `GITHUB_REPOS` | 逗號分隔 `owner/repo`，追蹤 commit（空＝不追）。 | 空 |
| `CODE_ROOT` | 本機專案母資料夾（子資料夾＝一個專案），供 owner 程式委派。 | 空 |
| `CODE_ASK_BUDGET_USD` / `CODE_APPLY_BUDGET_USD` | 程式問答/計畫、改碼+PR 的花費上限（美元）。 | `2` / `15` |
| `TAVILY_API_KEY` | 時事搜尋金鑰（tavily.com）。 | 空 |
| `KB_PATH` | SQLite 知識庫路徑。 | `~/.n/kb.sqlite` |
| `TG_API_ID` / `TG_API_HASH` | 僅離線灌 Telegram 歷史（MTProto）時用，一般免。 | 空 |

**功能開關**（建議用控制台「動作工具／網站瀏覽」卡開關；以下為 `.env` 對應，預設全關）：

| 變數 | 功能 |
|------|------|
| `MEDIA_ENABLED` | 媒體工具（圖片去背/轉檔/調尺寸；需 `rembg`，文件轉檔另需 LibreOffice）。 |
| `SEARCH_ENABLED` | 時事搜尋（需 `TAVILY_API_KEY`）。 |
| `IMAGE_GEN_ENABLED` | 自動配圖（Pollinations.AI，免金鑰）。 |
| `BROWSE_ENABLED` | 網站瀏覽（Playwright Chromium，CDP `localhost:9222`）。 |
| `ACTIONS_ENABLED` | 行事曆動作（macOS）。 |
| `EMAIL_ENABLED` | 收發信（macOS）。 |

> **安全**：面板讀金鑰/token 的 API **只回傳「是否已設定」的布林值、永遠不吐明文**；面板綁定 localhost，並有跨來源／Host 保護。

---

## 控制台逐卡說明

`.venv/bin/python -m panel` 開原生視窗（亮/暗主題）。頂部控制列：**啟動／停止／重啟 bot ＋ 即時 log**。

| 卡片 | 用途 |
|------|------|
| **身份設定** | 名字／職稱／公司／專案／團隊／老闆／轉介規則 → 寫入 `owner_profile.json`。助理名稱自動＝「名字 的助理」。 |
| **請假與本週重點** | 狀態（依日期區間自動判定）／請假期間（日曆選區間）／**方向框＋「幫我擬本週重點」**（LLM 草擬）／本週重點／**請假期間彙整**按鈕。 |
| **Telegram** | Bot Token（遮罩）＋白名單同事（id＋別名，別名僅顯示用）。 |
| **模型** | 一般模型／高階模型（可點選本地模型）＋「重新整理」可用模型清單＋檢索門檻＋各供應商金鑰（遮罩）＋相容端點。 |
| **重建索引** | Obsidian 路徑＋GitHub repos；一鍵重建知識庫（即時進度 log）。 |
| **動作工具** | 寄件帳號（選填）＋媒體工具／時事搜尋（含 Tavily 金鑰）／自動配圖 開關。 |
| **網站瀏覽** | 啟用網站瀏覽（首次下載專用 Chromium ~150MB；在專用視窗登入要瀏覽的網站）。 |
| **分析** | 在面板輸入問題 → 廣撈知識庫＋強模型 → 產出 HTML 報告（面板用，也可私訊 `分析：`）。 |

> 大多數設定改完需**重啟 bot** 生效（白名單即時生效、分析模式免重啟）。

---

## 怎麼用：你本人 / 同事 / 群組

### 你本人（私訊，`OWNER_CHAT_ID`）

直接私訊 bot 即可。除了一般問答（會查知識庫），這些是**關鍵字／指令**（多為私訊限定，括號標註）：

| 你打的話 | 觸發 |
|----------|------|
| 任何問題 | 知識庫問答（查不到會誠實說，並可問你要不要記進 Obsidian） |
| `分析：<問題>` | 深度分析 → HTML 報告存 Obsidian Inbox 並自動開啟（私訊限定） |
| 回「`存`」 | 把上一則知識問答存進 Obsidian `00_Raw/Inbox`（私訊限定） |
| 傳圖/檔 ＋「幫我去背 / 轉成 pdf / 縮到 1080 寬」 | 媒體工具（私訊＋群組） |
| 接著只打「去背」 | 對剛傳的那張圖下指令（媒體跟進；私訊＋群組） |
| 「幫我畫一隻貓…」 | 自動配圖（私訊＋群組） |
| 「今天台積電股價？／台北天氣？」 | 時事搜尋 Tavily（私訊；可設定開放群組） |
| 「幫我看 example.com／截圖…」 | 網站瀏覽（私訊限定，送出/發布前會問你確認） |
| 問某專案的程式問題 → 回「`修復計畫`」→ 回「`執行`」 | 程式委派：問答 → 擬計畫 → 改碼開 PR（私訊限定） |
| 「幫我在行事曆新增…／收信摘要」 | 行事曆/收發信（macOS，私訊限定，寫入前確認） |

### 同事（白名單內）

私訊或群組 @ 它，會走「**你的助理**」人設：

- 只依知識庫回答；查不到的通用/技術問題會盡力答，但**涉及你的私事且無資料 → 誠實說沒資料、幫你轉達，絕不編造**。
- **時效性問題**（股價/天氣/新聞，同事沒有搜尋權）→ 誠實說查不到即時資訊、建議問你或自查，**不拿舊資料硬掰**。
- **冷卻閘**防洗版：10 分鐘內超過 5 則、且整批被判定為「閒聊/不急」→ 鎖 60 分鐘並回「我先忙一下…」。你本人與老闆豁免。單純問一句非公事**不會**被擋。

### 群組

- bot **只在被 @ 時回應**；但會記錄群組所有訊息建立脈絡。
- 非白名單的人 @ 它 → 婉拒。
- **你本人在群組（被 @）** 可用：生圖、媒體工具、時事搜尋。
- 群組**擋掉**：網站瀏覽、行事曆、收發信、程式委派、分析、存 Inbox —— 且 bot 會**誠實說「這要私訊才能做」**，不會假裝在處理。

---

## 私訊 vs 群組 功能對照表

| 功能 | 你本人・私訊 | 你本人・群組（被 @） | 同事 |
|------|:---:|:---:|:---:|
| 知識庫問答 | ✅ | ✅ | ✅（同事人設） |
| 時事搜尋（Tavily） | ✅ | ✅ | ❌（會誠實說查不到） |
| 生圖 | ✅ | ✅ | ❌ |
| 媒體工具（去背/轉檔） | ✅ | ✅ | ❌ |
| 網站瀏覽 | ✅ | ❌ | ❌ |
| 行事曆 / 收發信 | ✅ | ❌ | ❌ |
| 程式委派 | ✅ | ❌ | ❌ |
| 分析模式 `分析：` | ✅ | ❌ | ❌ |
| 存進 Obsidian Inbox | ✅ | ❌ | ❌ |

---

## 運作原理

### 整體架構與資料流

```mermaid
flowchart TB
    subgraph SRC["知識來源"]
        OB["Obsidian vault"]
        GH["GitHub commits"]
        TGH["Telegram 歷史"]
    end
    OB --> ING["backfill.py / 重建索引"]
    GH --> ING
    TGH --> ING
    ING --> KB[("SQLite 知識庫<br/>~/.n/kb.sqlite · chunks + FTS5")]

    USER["同事 / 你本人"] -->|"私訊 / 群組 @"| BOT["bot.py<br/>Telegram long polling · 白名單過濾"]
    BOT --> ASST["assistant.py<br/>compose_reply（人設＋本週重點＋脈絡）"]
    KB -->|"混合檢索<br/>dense + FTS5 + RRF + rerank"| ASST
    ASST <-->|"依模型名前綴路由"| LLM{{"LLM 閘道<br/>Gemini / Claude / OpenAI / Ollama"}}
    ASST -.->|"時事問題"| TAV["Tavily 搜尋"]
    TAV -.-> ASST
    ASST -->|"回覆＋來源"| BOT
    BOT --> USER

    PANEL["控制台<br/>Flask + pywebview :8765"] -.->|"設定 / 金鑰"| CFG[(".env · owner_profile.json")]
    CFG -.-> BOT
    PANEL -.->|"啟動 / 停止 / 重啟 · 重建索引"| BOT
```

### 訊息路由決策流程

```mermaid
flowchart TD
    A["收到訊息"] --> B{"群組？"}
    B -->|"是"| C["記錄到 group_memory"]
    C --> D{"有 @ 到 bot？"}
    D -->|"否"| E["不回應（只記錄脈絡）"]
    D -->|"是"| F{"白名單 / owner？"}
    B -->|"否（私訊）"| F
    F -->|"非白名單"| G["婉拒"]
    F -->|"是"| H{"是 owner 本人？"}
    H -->|"同事"| I{"高頻＋低優先？"}
    I -->|"是"| J["冷卻鎖 60 分"]
    I -->|"否"| K["同事模式回覆<br/>誠實・不編造・無即時就說查不到"]
    H -->|"owner"| L{"動作關鍵字？"}
    L -->|"分析：/ 存 / 瀏覽 / 行事曆 / 委派<br/>（私訊限定）"| M["執行；在群組則說要私訊"]
    L -->|"生圖 / 媒體 / 時事搜尋<br/>（私訊＋群組）"| N["執行動作"]
    L -->|"一般問題"| O["本人模式回覆<br/>查知識庫＋可搜尋"]
```

**知識庫與檢索**：知識庫是單一檔 `~/.n/kb.sqlite`（`chunks` 表＋FTS5）。檢索＝dense 向量（numpy 餘弦）＋FTS5 全文＋RRF 融合＋rerank，低於門檻就傾向誠實說資料不足。來源：Obsidian（`ingest/obsidian.py`，依 frontmatter 日期/mtime 補 `event_time` 以支援「近期筆記」）、GitHub commits（`github_sync.py`）、Telegram 歷史。用 `backfill.py` 或面板「重建索引」重建。

---

## 請假、本週重點、請假彙整

- **請假狀態**：以你在面板設定的**日期區間**自動判定（不是從自由文字猜）。在請假區間內 → 同事會被告知你請假、何時回來。
- **本週重點**：always-on 的背景／交接資訊（不限請假時，平常同事問答也會參考）。可按「**幫我擬本週重點**」用高階模型從近期對話／commits／近期筆記／一句方向草擬，編修後再按「儲存請假設定」（AI 只出初稿、人把關，不自動存）。
- **請假期間彙整**：面板按「請假期間彙整」→ 把請假區間內「同事與助理的對話」整理成「已處理項目＋待辦/需你決定」，面板顯示並一併發到你 TG；**請假結束時 bot 也會自動 DM 你一次**。需先設好請假日期才會觸發（沒設不會動用模型）。

---

## 資料儲存（`~/.n/`）

所有本機資料都在家目錄的 `~/.n/`（不進版控）：

| 檔案 | 內容 |
|------|------|
| `kb.sqlite` | 知識庫（chunks＋FTS5）＋ per-人對話記憶。 |
| `allowlist.json` | 白名單同事 `[{id, alias}]`。 |
| `group_conversations.json` | 各群組最近對話（建立脈絡，per-chat）。 |
| `browse_allowlist.json` | 網站瀏覽的網域白名單。 |
| `chrome-browse-profile/` | 瀏覽用專用 Chromium 的 profile（cookie/登入）。 |
| `leave_digest_sent.txt` | 記錄請假彙整已自動發送，避免重發（發過才會出現）。 |

---

## 專案結構

```
jayvis/
├── bot.py              # live 入口：Telegram Bot（long polling）、所有訊息路由
├── assistant.py        # 組回覆：檢索 → 人設 → 模型（本人/同事/群組模式）
├── analysis.py         # 分析模式：廣撈 → 強模型 → HTML 報告（+接續修改）
├── focus_draft.py      # LLM 代擬「本週重點」草稿
├── leave_digest.py     # 請假期間彙整（同事項目+待辦；自動 DM）
├── websearch.py        # 時事搜尋：LLM 判斷該不該查 + Tavily
├── image_gen.py        # 自動配圖（Pollinations.AI）
├── browse_*.py         # 網站瀏覽（Playwright Chromium / CDP / 白名單 / 啟動看門狗）
├── code_delegate.py    # owner 程式委派（headless Coding Agent）
├── agent.py            # owner 動作工具（行事曆/收發信/媒體）派工
├── cooldown.py         # 同事冷卻閘（高頻+低優先 → 鎖）
├── llm.py              # 多供應商 LLM 閘道（Gemini/Claude/OpenAI/Ollama）
├── memory.py / group_memory.py  # per-人私訊記憶 / 群組對話
├── persona.py          # 人設組裝（owner_profile + 模板）
├── github_sync.py      # GitHub commit 摘要（TTL 快取）
├── backfill.py         # 建知識庫（Obsidian + GitHub → kb.sqlite）
├── config.py           # 中央設定（env 驅動：模型/路徑/id/旗標…）
├── guard.py / safety.py # prompt injection 防護
├── db/                 # SQLite 連線 + schema（chunks + FTS5）
├── retrieval/          # 混合檢索 · rerank · 信心（誠實說資料不足）
├── ingest/             # Obsidian / GitHub / Telegram 切塊 + 灌入
├── panel/              # 控制台（Flask + pywebview）
│   ├── app.py  botctl.py  env_io.py  __main__.py  static/
├── prompts/            # persona_template.md · *.example.json/md（使用者檔 gitignore）
└── tests/              # pytest（702 passed / 3 skipped）
```

---

## 換人使用（多租戶）

身份不寫死。要把 JAYVIS 給別人變成「他的」助理：

1. 改 `prompts/owner_profile.json`（或面板「身份設定」卡）—— 名字、團隊、轉介規則等。
2. 每個人保留自己本機的 `~/.n/kb.sqlite`（單一 owner、無 Postgres）。
3. 填自己的模型金鑰，或把 `OPENAI_BASE_URL` 指向本地 Ollama。
4. 白名單在 `~/.n/allowlist.json`（`[{id, alias}]`）。

> 身份／別名／模型／請假設定改完需**重啟 bot**（面板「重啟」鈕）。分析模式即時、免重啟。

---

## 常見問題 FAQ

**Q：群組 @ 它沒反應？**
A：99% 是 Telegram **群組隱私模式**沒關。私訊正常但群組收不到，就是它。照「快速開始 步驟 5」：BotFather `/setprivacy` → Disable → **移出再重加群組**（或把 bot 設群組管理員）。

**Q：模型端點名稱填什麼？**
A：模型名前綴決定供應商：`gemini-*`→Google、`claude-*`→Anthropic、`gpt-*`/`o*`→OpenAI、其它（如 `gemma:12b`、`qwen3:8b`）→走 `OPENAI_BASE_URL`（本地 Ollama 免金鑰）。面板「模型」卡的「重新整理」可列出各家可用模型。

**Q：改了設定沒生效？**
A：多數設定（人設、本週重點、token、模型、動作工具）是 bot 啟動時讀入，改完要按面板「**重啟**」。白名單即時生效、分析模式免重啟。

**Q：同事問非公事會被擋嗎？**
A：不會。單純一句非公事照樣盡力回（通用知識）。只有「短時間連發一堆閒聊」才會踩到冷卻閘鎖 60 分；不在白名單則一律婉拒。

**Q：同事沒有搜尋，問時事會亂答嗎？**
A：不會。同事問時效性問題（股價/天氣/新聞）時，助理會誠實說「查不到即時資訊、建議問本人或自查」，不拿過時記憶硬掰。

---

## 測試

```bash
.venv/bin/python -m pytest tests/ -q
```

目前 **702 passed / 3 skipped**。測試用 `pytest-randomly`（順序無關），KB 與 group_memory 在測試中皆導向暫存路徑，不污染正式資料。

---

## 授權

MIT —— 見 [LICENSE](LICENSE)。
