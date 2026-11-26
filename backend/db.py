"""SQLite storage. One fixed schema serves every app: specs and submissions are JSON.

The workspace runs in one of three modes, each with its own data folder:
  university - faculty, students, staff; departments, sections, year groups, clubs
  office     - employees and managers; departments and teams
  general    - personal use; apps are usually shared with "anyone with the link"
"""
import json
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE = os.environ.get("APPSHARE_MODE", "university").strip().lower()
if MODE not in ("university", "office", "general"):
    MODE = "university"
DATA_ROOT = os.environ.get("APPSHARE_DATA", os.path.join(BASE_DIR, "data"))
DATA_DIR = os.path.join(DATA_ROOT, MODE)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "appshare.db")

ORG_NAME = os.environ.get("APPSHARE_ORG") or {
    "university": "Riverside University", "office": "Northwind Labs", "general": "AppShare"}[MODE]

# Words the interface and the agents use in each mode.
VOCAB = {
    "university": {"org": ORG_NAME, "people": "students and staff", "group_kinds": {
        "department": "Department", "section": "Section", "year": "Year group", "club": "Club", "staff": "Staff", "everyone": "Everyone"},
        "default_access": "restricted", "member": "member of the university"},
    "office": {"org": ORG_NAME, "people": "employees", "group_kinds": {
        "department": "Department", "team": "Team", "everyone": "Everyone"},
        "default_access": "restricted", "member": "employee"},
    "general": {"org": ORG_NAME, "people": "people", "group_kinds": {"list": "List"},
        "default_access": "public", "member": "user"},
}[MODE]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',        -- e.g. "Professor · CSE", "Backend Engineer"
    kind TEXT NOT NULL DEFAULT 'member',   -- student | faculty | staff | employee | manager | member
    is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
    kind TEXT NOT NULL DEFAULT 'group',    -- department | section | year | club | staff | team | everyone | list
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, user_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS apps (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    spec TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',          -- draft | published | closed
    link_access TEXT NOT NULL DEFAULT 'restricted', -- restricted | org | public
    share_suggestions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    principal_type TEXT NOT NULL,   -- user | group
    principal_id INTEGER NOT NULL,
    role TEXT NOT NULL,             -- editor | viewer | submitter
    UNIQUE (app_id, principal_type, principal_id)
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),           -- NULL for a guest answering a public link
    guest_key TEXT,                                 -- the guest's device id (one response per device)
    guest_name TEXT,
    guest_email TEXT,
    data TEXT NOT NULL,
    status TEXT,                                    -- for request apps: e.g. Pending / Approved
    status_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    submission_id INTEGER REFERENCES submissions(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    field_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    submission_id INTEGER PRIMARY KEY REFERENCES submissions(id) ON DELETE CASCADE,
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL,           -- ok | check | problem
    summary TEXT NOT NULL,
    flags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_id INTEGER REFERENCES apps(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,              -- reminder | review | status | shared
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS reminder_log (
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,             -- day | hour | manual-<timestamp>
    sent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (app_id, stage)
);
CREATE TABLE IF NOT EXISTS agent_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,              -- builder | insights
    app_id INTEGER REFERENCES apps(id) ON DELETE CASCADE,
    messages TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA journal_mode = WAL")
        _migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            from . import seed
            seed.seed(conn, MODE)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('mode', ?), ('org', ?)", (MODE, ORG_NAME))


# Columns added after the first release: created on start if an older database lacks them (data is kept).
MIGRATIONS = {"reviews": {"evidence": "TEXT", "guard": "TEXT", "decision": "TEXT", "decided_by": "TEXT", "decided_at": "TEXT"}}


def _migrate(conn):
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def add_user(conn, email, name, groups, is_admin=0, title="", kind="member", group_kinds=None, descriptions=None):
    email = email.strip().lower()
    conn.execute(
        "INSERT INTO users (email, name, title, kind, is_admin) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(email) DO UPDATE SET name = excluded.name",
        (email, name.strip(), title, kind, is_admin),
    )
    uid = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    for g in groups:
        g = g.strip()
        if not g:
            continue
        conn.execute("INSERT OR IGNORE INTO groups (name, kind, description) VALUES (?, ?, ?)",
                     (g, (group_kinds or {}).get(g, "group"), (descriptions or {}).get(g, "")))
        gid = conn.execute("SELECT id FROM groups WHERE name = ?", (g,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)", (gid, uid))
    return uid


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
