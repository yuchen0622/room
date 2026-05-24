from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DORM_REPAIR_DB_PATH", "data/app.db"))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_db() -> sqlite3.Connection:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('student','repairman','admin')),
              dorm_building TEXT,
              dorm_room TEXT,
              phone TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS repair_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              student_id INTEGER NOT NULL,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              location_building TEXT NOT NULL,
              location_room TEXT NOT NULL,
              contact_phone TEXT,
              status TEXT NOT NULL CHECK(status IN ('submitted','assigned','in_progress','done','rejected','cancelled')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS work_orders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id INTEGER NOT NULL UNIQUE,
              assigned_to INTEGER,
              status TEXT NOT NULL CHECK(status IN ('open','assigned','in_progress','done','rejected','cancelled')),
              note TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              finished_at TEXT,
              FOREIGN KEY(request_id) REFERENCES repair_requests(id) ON DELETE CASCADE,
              FOREIGN KEY(assigned_to) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS announcements (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )

