"""Storage adapter #1: durable webxdc ops log on libSQL (Turso-compatible).

Persists one webxdc instance's status-update stream plus the bot's high-water
serial, so nothing the shared-list app sends is lost and the bot can resume
after restarts. Merging/conflict resolution stays with the app's canonical
MergeDoc (JVM/JS); this store guarantees durability and replay only.

Serials are LOCAL to this bot profile's view of the instance - the same
numbering the app-side setUpdateListener(cb, serial) replays from. Global
ordering lives in the ops' HLC stamps, kept untouched inside payload.

Local file today. The Turso cloud step is a constructor change
(url="libsql://<db>.turso.io", auth_token=...); the interface is identical.
Cloud path is untested until the user creates/approves a Turso database.
"""

import json
import os
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS webxdc_ops (
  serial INTEGER PRIMARY KEY,
  payload TEXT NOT NULL,
  info TEXT,
  received_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS webxdc_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class OpsStore:
    def __init__(self, url="ops.db", auth_token=None):
        force_sqlite = os.environ.get("OPS_STORE_FORCE_SQLITE") == "1"
        if auth_token or url.startswith(("libsql://", "https://")):
            import libsql_experimental as libsql
            self.conn = libsql.connect(url, auth_token=auth_token) if auth_token else libsql.connect(url)
        elif not force_sqlite:
            try:
                import libsql_experimental as libsql
                self.conn = libsql.connect(url)
            except ImportError:
                force_sqlite = True
        if force_sqlite:
            # Termux/phone path: stdlib sqlite3 (libSQL is SQLite-compatible).
            import sqlite3
            self.conn = sqlite3.connect(url)
        self.conn.executescript(SCHEMA)

    def watermark(self):
        row = self.conn.execute("SELECT value FROM webxdc_meta WHERE key='last_serial'").fetchone()
        return int(row[0]) if row else 0

    def apply_updates(self, updates):
        """Idempotently apply get_webxdc_status_updates() output. Returns count of new rows."""
        new = 0
        wm = self.watermark()
        for u in updates:
            serial = u["serial"]
            exists = self.conn.execute("SELECT 1 FROM webxdc_ops WHERE serial=?", (serial,)).fetchone()
            if exists:
                continue
            self.conn.execute(
                "INSERT INTO webxdc_ops(serial, payload, info, received_at) VALUES (?,?,?,?)",
                (serial, json.dumps(u.get("payload")), u.get("info"), int(time.time())),
            )
            new += 1
            if serial > wm:
                wm = serial
        self.conn.execute(
            "INSERT INTO webxdc_meta(key,value) VALUES('last_serial',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(wm),),
        )
        self.conn.commit()
        return new

    def ops_since(self, serial=0):
        rows = self.conn.execute(
            "SELECT serial, payload, info FROM webxdc_ops WHERE serial>? ORDER BY serial", (serial,)
        ).fetchall()
        return [(r[0], json.loads(r[1]), r[2]) for r in rows]

    def count(self):
        return self.conn.execute("SELECT count(*) FROM webxdc_ops").fetchone()[0]
