CREATE TABLE IF NOT EXISTS chunks (
    id             TEXT PRIMARY KEY,
    source_type    TEXT NOT NULL,
    owner          TEXT NOT NULL DEFAULT 'owner',
    repo           TEXT,
    file_path      TEXT,
    commit_sha     TEXT,
    pr_number      INTEGER,
    channel        TEXT,
    thread_id      TEXT,
    speaker        TEXT,
    permalink      TEXT,
    doc_path       TEXT,
    export_version TEXT,
    author         TEXT,
    event_time     TEXT,
    ingested_at    TEXT NOT NULL DEFAULT (datetime('now')),
    raw_text       TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    embedding      BLOB
);

CREATE INDEX IF NOT EXISTS chunks_owner_source ON chunks(owner, source_type);

-- 全文檢索（FTS5 trigram，中文友善，免擴充）
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
    USING fts5(raw_text, content='chunks', content_rowid='rowid', tokenize='trigram');

-- external-content 同步 trigger
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, raw_text) VALUES (new.rowid, new.raw_text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, raw_text) VALUES('delete', old.rowid, old.raw_text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, raw_text) VALUES('delete', old.rowid, old.raw_text);
    INSERT INTO chunks_fts(rowid, raw_text) VALUES (new.rowid, new.raw_text);
END;

-- 搭檔記憶：時間軸日誌（對談/動作/媒體），每筆強制時間戳
CREATE TABLE IF NOT EXISTS memories (
    id           TEXT PRIMARY KEY,
    ts           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    person_id    TEXT NOT NULL,
    person_alias TEXT,
    kind         TEXT NOT NULL,
    content      TEXT NOT NULL,
    meta         TEXT,
    chunk_id     TEXT
);
CREATE INDEX IF NOT EXISTS memories_person_ts ON memories(person_id, ts);

CREATE TABLE IF NOT EXISTS note_meta (
    doc_path TEXT PRIMARY KEY,
    title    TEXT,
    is_moc   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS note_links (
    src TEXT NOT NULL,        -- doc_path（來源筆記）
    dst TEXT NOT NULL         -- doc_path（被連到的筆記）
);
CREATE INDEX IF NOT EXISTS note_links_src ON note_links(src);
CREATE INDEX IF NOT EXISTS note_links_dst ON note_links(dst);

CREATE TABLE IF NOT EXISTS person_profiles (
    person_id  TEXT PRIMARY KEY,
    profile    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
