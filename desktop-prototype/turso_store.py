"""Storage adapter #1b: Turso cloud over plain HTTPS (Python stdlib only).

Same ops-log + watermark interface as OpsStore, talking to a Turso database's
SQL-over-HTTP endpoint (POST /v2/pipeline, Bearer token; official reference:
https://docs.turso.tech/sdk/http/reference). urllib only - no native wheel -
so it runs on Termux as-is, unlike libsql-experimental.

STATUS: protocol shaping and parsing are unit-tested against a local stub
that executes the SQL in sqlite3 (test_turso_store.py). It has NEVER run
against a real Turso database - none exists yet; creating one and minting a
token is the user's decision, and the token would live only in the bot's
environment on the phone.
"""

import json
import urllib.request

SCHEMA_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS webxdc_ops (serial INTEGER PRIMARY KEY, payload TEXT NOT NULL, info TEXT, received_at INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS webxdc_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
]


def _val(v):
    if v is None:
        return {"type": "null", "value": None}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _cell(c):
    t, v = c["type"], c["value"]
    if t == "null":
        return None
    if t == "integer":
        return int(v)
    if t == "float":
        return float(v)
    return v  # text; we never store blobs


class TursoHTTPStore:
    def __init__(self, base_url, auth_token, opener=None):
        self.base = base_url.rstrip("/")
        self.token = auth_token
        self.opener = opener or urllib.request.urlopen
        self._pipeline([(s, ()) for s in SCHEMA_STATEMENTS])

    def _pipeline(self, stmts):
        reqs = [
            {"type": "execute", "stmt": {"sql": sql, "args": [_val(a) for a in args]}}
            for sql, args in stmts
        ]
        reqs.append({"type": "close"})
        req = urllib.request.Request(
            self.base + "/v2/pipeline",
            data=json.dumps({"requests": reqs}).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(req, timeout=30) as resp:
            data = json.loads(resp.read())
        out = []
        for r in data["results"][:-1]:  # last entry answers "close"
            if r["type"] != "ok":
                raise RuntimeError("turso pipeline error: %s" % json.dumps(r))
            res = r["response"]["result"]
            cols = [c["name"] for c in res["cols"]]
            rows = [[_cell(c) for c in row] for row in res["rows"]]
            out.append((cols, rows, res["affected_row_count"]))
        return out

    def watermark(self):
        _, rows, _ = self._pipeline([("SELECT value FROM webxdc_meta WHERE key='last_serial'", ())])[0]
        return int(rows[0][0]) if rows else 0

    def apply_updates(self, updates):
        """Idempotent by serial (INSERT OR IGNORE). Returns count of new rows."""
        if not updates:
            return 0
        import time
        stmts = [
            ("INSERT OR IGNORE INTO webxdc_ops(serial, payload, info, received_at) VALUES (?,?,?,?)",
             (u["serial"], json.dumps(u.get("payload")), u.get("info"), int(time.time())))
            for u in updates
        ]
        wm = max(u["serial"] for u in updates)
        stmts.append((
            "INSERT INTO webxdc_meta(key,value) VALUES('last_serial',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE CAST(webxdc_meta.value AS INTEGER) < CAST(excluded.value AS INTEGER)",
            (str(wm),),
        ))
        results = self._pipeline(stmts)
        return sum(affected for _, _, affected in results[:-1])

    def ops_since(self, serial=0):
        _, rows, _ = self._pipeline([(
            "SELECT serial, payload, info FROM webxdc_ops WHERE serial>? ORDER BY serial", (serial,))])[0]
        return [(r[0], json.loads(r[1]), r[2]) for r in rows]

    def count(self):
        _, rows, _ = self._pipeline([("SELECT count(*) FROM webxdc_ops", ())])[0]
        return rows[0][0]
