# JAYVIS

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB" />
  <img src="https://img.shields.io/badge/Telegram-Bot%20API-26A5E4" />
  <img src="https://img.shields.io/badge/SQLite-FTS5%20%2B%20numpy-003B57" />
  <img src="https://img.shields.io/badge/Flask%20%2B%20pywebview-Control%20Panel-000000" />
  <img src="https://img.shields.io/badge/LLM-Gemini%20%C2%B7%20Claude%20%C2%B7%20OpenAI%20%C2%B7%20Ollama-F3B54A" />
  <img src="https://img.shields.io/badge/license-MIT-success" />
</p>

> **JAYVIS** is a self-hosted personal Telegram AI assistant. When you are away,
> colleagues can DM it or @-mention it in a work group, and it answers in your
> voice — grounded in your own knowledge base (Obsidian notes, GitHub commits,
> Telegram history). It ships with a desktop **control panel** to configure
> everything, runs **local-first** (single-file SQLite, no Postgres), and is
> easy to hand to someone else to run as their own assistant.

---

## Features

| Feature | Description |
|---------|-------------|
| **RAG knowledge Q&A** | Hybrid retrieval over Obsidian + GitHub commits + Telegram history (dense + FTS5 + RRF) with a reranker; **abstains** (with sources) when confidence is low instead of guessing. |
| **Owner / colleague modes** | The owner gets a candid private assistant; colleagues get an honest "assistant" persona that never impersonates you and never fabricates personal facts. |
| **Auto leave replies** | When you are on leave, the assistant tells colleagues your status and return date — derived automatically from a date range. |
| **Group context** | When @-mentioned in a group, it pulls in the group's recent messages so replies fit the ongoing discussion. |
| **Multi-provider model routing** | Routes by model name to **Gemini / Claude / OpenAI / local Ollama**; API keys are masked in the panel. |
| **Allowlist + aliases** | Only replies to allowlisted Telegram users; optional aliases let it address people naturally. |
| **Control panel app** | A native window to manage identity, leave, allowlist, models, knowledge re-index, and analysis — with light/dark themes. |
| **Local-first, no Postgres** | Single-file SQLite knowledge base + local embeddings; no database server required. |
| **Optional code delegation** | Owner-only: delegate code questions / fixes for local project folders to a code model. |
| **Optional action tools** *(macOS)* | Owner-only calendar, mail, and media (image/document) tools, all off by default and gated behind explicit confirmation. |

---

## Tech stack

| Layer | Technology |
|-------|------------|
| **Entry point** | Python 3.11 · `python-telegram-bot` (Bot API, long polling) |
| **Knowledge base** | SQLite (FTS5 trigram) + numpy cosine + Python RRF fusion (zero servers) |
| **Embedding / rerank** | sentence-transformers (e.g. `BAAI/bge-m3`, `bge-reranker-v2-m3`) |
| **LLM** | google-genai (Gemini, Vertex or API key) · Anthropic · OpenAI · local Ollama (OpenAI-compatible) |
| **Control panel** | Flask + pywebview (native window, light/dark themes) |
| **Knowledge sources** | Obsidian vault · GitHub commits · Telegram history |

---

## Quick start

### 1. Install

```bash
git clone <your-fork-url> jayvis && cd jayvis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in keys (see Configuration below)
```

### 2. Provide your config

You can configure JAYVIS either through the **control panel** (recommended) or
by editing files directly. The personal config files are gitignored and written
at runtime by the panel:

- `prompts/owner_profile.json` — your identity (name, title, company, projects,
  team, routing). A generic template lives at `prompts/owner_profile.example.json`;
  copy it or fill the panel's "Identity" card.
- `prompts/WeeklyFocus.md` — your weekly focus + leave dates. Template at
  `prompts/WeeklyFocus.example.md`.

If these files are absent, JAYVIS automatically falls back to the `.example`
versions so it still runs out of the box.

### 3. Build the knowledge base (optional)

```bash
python backfill.py            # first run downloads the embedding model; builds ~/.n/kb.sqlite
```

### 4. Run

```bash
python -m panel               # control panel (recommended: configure + start/stop the bot)
# or
python bot.py                 # run the bot directly (long polling, no public URL needed)
```

> For group context, set **@BotFather → `/setprivacy` → Disable**, then remove and re-add the bot to the group.

---

## Configuration

All real config is environment-driven (`.env`) or written by the control panel.
Nothing personal is committed. Key variables:

| Variable | Description |
|----------|-------------|
| `TG_BOT_TOKEN` | Bot token from **@BotFather**. |
| `OWNER_CHAT_ID` | Your numeric Telegram id — the only user who can trigger owner-mode and action tools (`0` = disabled). |
| `ALLOWLIST_USER_IDS` | Comma-separated numeric ids allowed to talk to the bot. |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Model keys — set whichever providers you use. |
| `OPENAI_BASE_URL` | Optional: OpenAI-compatible endpoint (e.g. a local Ollama at `http://localhost:11434/v1`). |
| `MODEL_GENERAL` / `MODEL_CODE` | Model names; provider is inferred from the name prefix. |
| `OBSIDIAN_PATH` | Path to your Obsidian vault (leave empty to skip Obsidian ingest). |
| `GITHUB_REPOS` | Comma-separated `owner/repo` to track commits (empty = none). |
| `CODE_ROOT` | Parent folder of local project folders, for owner-only code delegation. |
| `CODE_MODEL` | Model used for code delegation. |
| `KB_PATH` | SQLite knowledge base path (default `~/.n/kb.sqlite`). |

See `.env.example` for the full annotated list.

> **Personal config is gitignored.** `prompts/owner_profile.json`,
> `prompts/WeeklyFocus.md`, `prompts/obsidian_folders.json`, your `.env`, and the
> local data dir `~/.n/` are never committed — only the `.example` templates are.

---

## How it works

```
Colleague DM / group @-mention
        ↓
Telegram bot (bot.py · long polling · allowlist filter)
        ↓
Hybrid retrieval: Obsidian + GitHub + Telegram → SQLite (dense + FTS5 + RRF) + rerank
        ↓  (low confidence → abstain; in groups, conversation context relaxes this)
System prompt = persona (owner_profile) + weekly focus + retrieved snippets + recent group messages
        ↓
LLM (Gemini / Claude / OpenAI / Ollama, routed by model name)
        ↓
Reply as "<owner>'s personal AI assistant" (with sources)
```

---

## Project structure

```
jayvis/
├── bot.py              # live entry: Telegram Bot (long polling)
├── assistant.py        # builds the reply: retrieval → persona → model
├── analysis.py         # cross-corpus analysis (used by the panel)
├── llm.py              # multi-provider LLM gateway (Gemini / Claude / OpenAI / Ollama)
├── router.py           # general / code model routing
├── guard.py, safety.py # prompt-injection protection
├── group_memory.py     # recent group conversation (persisted, per-chat)
├── memory.py           # per-person DM memory
├── persona.py          # persona assembly (owner_profile + template)
├── github_sync.py      # GitHub commit summaries (TTL cache)
├── backfill.py         # build the knowledge base (Obsidian + GitHub → kb.sqlite)
├── config.py           # central config (env-driven: models, paths, ids…)
├── code_delegate.py    # owner-only code delegation
├── db/                 # SQLite connection + schema (chunks + FTS5)
├── retrieval/          # hybrid retrieval · rerank · confidence (abstain)
├── ingest/             # Obsidian / GitHub / Telegram chunking + ingest
├── panel/              # control panel (Flask + pywebview)
│   ├── app.py  botctl.py  env_io.py  static/
├── prompts/            # persona_template.md · *.example.json/md (user files are gitignored)
└── tests/              # pytest suite
```

---

## Control panel

`python -m panel` opens a native window (Flask + pywebview), light/dark themes:

| Card | Purpose |
|------|---------|
| **Identity** | Name / title / company / projects / team / routing → writes `prompts/owner_profile.json`. |
| **Leave** | Pick a leave date range (status is derived automatically); free-text weekly focus. |
| **Telegram** | Bot token (masked) + allowlisted colleagues (id + alias). |
| **Knowledge** | Obsidian path + GitHub repos; one-click re-index of the vector store. |
| **Models** | General / code models (local models selectable) + retrieval threshold + provider keys (masked) + compatible endpoint. |
| **Analysis** | Ask a question in the panel → broad knowledge-base recall + a strong model synthesizes (panel only, not over Telegram). |

> Security: key/token read endpoints only report a "configured" boolean and **never return plaintext**; the panel binds to localhost with cross-origin / Host protection.

---

## Action tools (owner-only, macOS)

When the owner DMs JAYVIS, optional tools can manage your own Mac's Calendar,
Mail, and media — all **off by default**, owner-only, and confirmation-gated.

> These tools are **macOS-only** (they drive Calendar.app / Mail.app via AppleScript).
> Every other JAYVIS feature is cross-platform; on non-macOS the bot replies that
> the action is unsupported instead of erroring.

---

## Multi-tenant

Identity is not hardcoded. To hand JAYVIS to someone else:

1. Edit `prompts/owner_profile.json` (or the panel "Identity" card) — name, team, routing, etc.
2. Each user keeps their own local `kb.sqlite` (single owner, no Postgres).
3. Set your own model keys, or point `OPENAI_BASE_URL` at a local Ollama.
4. The allowlist lives at `~/.n/allowlist.json` (`[{id, alias}]`).

> Identity / alias / model / leave changes require a bot restart (panel "Restart" button). Analysis mode is live and needs no restart.

---

## License

MIT — see [LICENSE](LICENSE).
