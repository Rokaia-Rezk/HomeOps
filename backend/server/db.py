import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL CHECK(role IN ('customer','tech','call','finance','admin')),
  name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT,
  pass_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  lang TEXT NOT NULL DEFAULT 'ar', addrs TEXT NOT NULL DEFAULT '[]',
  seeded INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL,
  UNIQUE(email, role));
CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY, email TEXT NOT NULL,
  svc TEXT NOT NULL, pr TEXT NOT NULL, place TEXT, syms TEXT NOT NULL DEFAULT '[]',
  descr TEXT, date TEXT, slot TEXT, addr TEXT, status TEXT NOT NULL, tech TEXT,
  files INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL,
  inv TEXT, paid_out INTEGER NOT NULL DEFAULT 0, paid_out_at INTEGER, triage TEXT);
CREATE TABLE IF NOT EXISTS tickets(
  id TEXT PRIMARY KEY, email TEXT, from_name TEXT, type TEXT, pr TEXT, text TEXT, ord TEXT,
  actions TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL, ts INTEGER NOT NULL, log TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, dir TEXT, who TEXT, note TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, actor TEXT, action TEXT);
CREATE TABLE IF NOT EXISTS expenses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, descr TEXT, amt REAL NOT NULL, kind TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters(name TEXT PRIMARY KEY, val INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS otps(
  email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires INTEGER NOT NULL, tries INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_orders_email ON orders(email);
CREATE INDEX IF NOT EXISTS ix_orders_tech ON orders(tech);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_tickets_email ON tickets(email);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def init(conn):
    conn.executescript(SCHEMA)
    conn.commit()
