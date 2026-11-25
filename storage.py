"""Storage backends for Tsebisa: local SQLite and hosted PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import os
import sqlite3


class DuplicateUserError(Exception):
    pass


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class SQLiteStore:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self):
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT, reference TEXT UNIQUE NOT NULL,
                submission_channel TEXT DEFAULT 'Website', category TEXT NOT NULL,
                description TEXT, location TEXT, phone TEXT, language TEXT DEFAULT 'st',
                status TEXT DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT,
                voice_note TEXT, photo TEXT)""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(reports)")}
            for name, sql_type in (("submission_channel", "TEXT DEFAULT 'Website'"), ("voice_note", "TEXT"), ("photo", "TEXT")):
                if name not in columns:
                    db.execute(f"ALTER TABLE reports ADD COLUMN {name} {sql_type}")
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, report_ref TEXT NOT NULL,
                sender_role TEXT NOT NULL, sender_name TEXT NOT NULL, message TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL, display_name TEXT)""")
            user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "display_name" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN display_name TEXT")

    def get_user(self, username):
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    def create_user(self, record):
        try:
            with self._db() as db:
                db.execute("INSERT INTO users (username,password_hash,role,display_name) VALUES (?,?,?,?)",
                           (record["username"], record["password_hash"], record["role"], record["display_name"]))
        except sqlite3.IntegrityError as exc:
            raise DuplicateUserError from exc

    def list_users(self):
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT id,username,role,display_name FROM users ORDER BY role,username")]

    def update_user_display_name(self, username, display_name):
        with self._db() as db:
            db.execute("UPDATE users SET display_name=? WHERE username=?", (display_name, username))

    def delete_user(self, user_id):
        with self._db() as db:
            db.execute("DELETE FROM users WHERE id=? AND username<>? AND role<>?", (user_id, "admin", "admin"))

    def create_report(self, record):
        try:
            with self._db() as db:
                fields = ("reference", "submission_channel", "category", "description", "location", "phone", "language", "status", "created_at", "voice_note", "photo")
                db.execute(f"INSERT INTO reports ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", tuple(record.get(k) for k in fields))
            return True
        except sqlite3.IntegrityError:
            return False

    def get_report(self, reference, fields=None):
        with self._db() as db:
            select = ",".join(fields) if fields else "*"
            row = db.execute(f"SELECT {select} FROM reports WHERE reference=?", (reference,)).fetchone()
            return dict(row) if row else None

    def list_reports(self, status=None, limit=None):
        sql = "SELECT * FROM reports"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._db() as db:
            return [dict(row) for row in db.execute(sql, params)]

    def update_report_status(self, reference, status, now):
        with self._db() as db:
            row = db.execute("SELECT status FROM reports WHERE reference=?", (reference,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE reports SET status=?,updated_at=? WHERE reference=?", (status, now, reference))
            return row["status"]

    def count_reports(self):
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    def add_message(self, record):
        with self._db() as db:
            db.execute("INSERT INTO conversations (report_ref,sender_role,sender_name,message,created_at) VALUES (?,?,?,?,?)",
                       tuple(record[k] for k in ("report_ref", "sender_role", "sender_name", "message", "created_at")))

    def list_messages(self, reference=None):
        with self._db() as db:
            if reference:
                rows = db.execute("SELECT sender_role,sender_name,message,created_at FROM conversations WHERE report_ref=? ORDER BY id", (reference,))
            else:
                rows = db.execute("SELECT report_ref,sender_role,sender_name,message,created_at FROM conversations ORDER BY id")
            return [dict(row) for row in rows]


class PostgresStore:
    """PostgreSQL backend for Neon and other PostgreSQL providers."""
    def __init__(self, database_url):
        if not database_url:
            raise RuntimeError("Set DATABASE_URL to the Neon PostgreSQL connection string.")
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.dict_row = dict_row
        self.database_url = database_url

    @contextmanager
    def _db(self):
        with self.psycopg.connect(self.database_url, row_factory=self.dict_row) as conn:
            yield conn

    def initialize(self):
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reports (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                reference TEXT UNIQUE NOT NULL,
                submission_channel TEXT DEFAULT 'Website', category TEXT NOT NULL,
                description TEXT, location TEXT, phone TEXT, language TEXT DEFAULT 'st',
                status TEXT DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT,
                voice_note TEXT, photo TEXT)""")
            db.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS submission_channel TEXT DEFAULT 'Website'")
            db.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS voice_note TEXT")
            db.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS photo TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                report_ref TEXT NOT NULL, sender_role TEXT NOT NULL, sender_name TEXT NOT NULL,
                message TEXT NOT NULL, created_at TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_report_ref ON conversations(report_ref, id)")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL, display_name TEXT)""")
            db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS feedback_log (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                report_ref TEXT, note TEXT, created_at TEXT)""")

    def get_user(self, username):
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()
            return dict(row) if row else None

    def create_user(self, record):
        try:
            with self._db() as db:
                db.execute("INSERT INTO users (username,password_hash,role,display_name) VALUES (%s,%s,%s,%s)",
                           (record["username"], record["password_hash"], record["role"], record["display_name"]))
        except self.psycopg.errors.UniqueViolation as exc:
            raise DuplicateUserError from exc

    def list_users(self):
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT id,username,role,display_name FROM users ORDER BY role,username").fetchall()]

    def update_user_display_name(self, username, display_name):
        with self._db() as db:
            db.execute("UPDATE users SET display_name=%s WHERE username=%s", (display_name, username))

    def delete_user(self, user_id):
        try:
            value = int(user_id)
        except (TypeError, ValueError):
            return
        with self._db() as db:
            db.execute("DELETE FROM users WHERE id=%s AND username<>%s AND role<>%s", (value, "admin", "admin"))

    def create_report(self, record):
        fields = ("reference", "submission_channel", "category", "description", "location", "phone", "language", "status", "created_at", "voice_note", "photo")
        try:
            with self._db() as db:
                db.execute(f"INSERT INTO reports ({','.join(fields)}) VALUES ({','.join('%s' for _ in fields)})",
                           tuple(record.get(key) for key in fields))
            return True
        except self.psycopg.errors.UniqueViolation:
            return False

    def get_report(self, reference, fields=None):
        with self._db() as db:
            if fields:
                allowed = {"reference", "submission_channel", "category", "description", "location", "phone", "language", "status", "created_at", "updated_at", "voice_note", "photo", "id"}
                if not set(fields) <= allowed:
                    raise ValueError("Unsupported report field")
                sql = f"SELECT {','.join(fields)} FROM reports WHERE reference=%s"
            else:
                sql = "SELECT * FROM reports WHERE reference=%s"
            row = db.execute(sql, (reference,)).fetchone()
            return dict(row) if row else None

    def list_reports(self, status=None, limit=None):
        sql, params = "SELECT * FROM reports", []
        if status:
            sql += " WHERE status=%s"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self._db() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def update_report_status(self, reference, status, now):
        with self._db() as db:
            row = db.execute("SELECT status FROM reports WHERE reference=%s", (reference,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE reports SET status=%s,updated_at=%s WHERE reference=%s", (status, now, reference))
            return row["status"]

    def count_reports(self):
        with self._db() as db:
            return db.execute("SELECT COUNT(*) AS total FROM reports").fetchone()["total"]

    def add_message(self, record):
        with self._db() as db:
            db.execute("INSERT INTO conversations (report_ref,sender_role,sender_name,message,created_at) VALUES (%s,%s,%s,%s,%s)",
                       tuple(record[key] for key in ("report_ref", "sender_role", "sender_name", "message", "created_at")))

    def list_messages(self, reference=None):
        sql = "SELECT report_ref,sender_role,sender_name,message,created_at FROM conversations"
        params = ()
        if reference:
            sql += " WHERE report_ref=%s"
            params = (reference,)
        sql += " ORDER BY id"
        with self._db() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]


def create_store(backend, sqlite_path, database_url=None):
    if backend in ("postgres", "neon"):
        return PostgresStore(database_url or os.environ.get("DATABASE_URL", ""))
    if backend != "sqlite":
        raise ValueError("TSEBISA_STORAGE_BACKEND must be 'sqlite' or 'neon'.")
    return SQLiteStore(sqlite_path)
