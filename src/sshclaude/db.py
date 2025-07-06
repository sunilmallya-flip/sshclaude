import os
import sqlite3
from contextlib import contextmanager

DB_URL = os.getenv("DATABASE_URL", "sshclaude.db")


def init_db() -> None:
    conn = sqlite3.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS tunnels (id INTEGER PRIMARY KEY AUTOINCREMENT, subdomain TEXT UNIQUE, tunnel_id TEXT, user_id INTEGER, FOREIGN KEY(user_id) REFERENCES users(id))"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS dns_access (id INTEGER PRIMARY KEY AUTOINCREMENT, dns_record_id TEXT, access_app_id TEXT, tunnel_id INTEGER, FOREIGN KEY(tunnel_id) REFERENCES tunnels(id))"
    )
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_URL)
    try:
        yield conn
    finally:
        conn.close()
