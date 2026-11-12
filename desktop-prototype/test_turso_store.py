"""TursoHTTPStore protocol test against a LOCAL STUB of /v2/pipeline.

The stub validates the hrana-over-HTTP envelope (typed args, Bearer header,
close appended) and executes the SQL in a real sqlite3 database, so the SQL
itself is exercised for real. This is NOT a test against a real Turso DB.
"""
import json, os, sqlite3, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from turso_store import TursoHTTPStore

TOKEN = "stub-token"
shapes = []

def to_py(v):
    t, x = v["type"], v["value"]
    return None if t == "null" else int(x) if t == "integer" else float(x) if t == "float" else x

class Stub(BaseHTTPRequestHandler):
    db_path = None
    def do_POST(self):
        assert self.path == "/v2/pipeline", self.path
        assert self.headers["Authorization"] == "Bearer " + TOKEN
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        shapes.append(body)
        assert body["requests"][-1]["type"] == "close"
        results = []
        conn = sqlite3.connect(self.db_path)
        for r in body["requests"][:-1]:
            stmt = r["stmt"]
            cur = conn.execute(stmt["sql"], [to_py(a) for a in stmt.get("args", [])])
            cols = [{"name": d[0]} for d in (cur.description or [])]
            rows = [[{"type": "null", "value": None} if v is None else
                     {"type": "integer", "value": str(v)} if isinstance(v, int) else
                     {"type": "text", "value": str(v)} for v in row] for row in cur.fetchall()]
            results.append({"type": "ok", "response": {"type": "execute", "result": {
                "cols": cols, "rows": rows, "affected_row_count": cur.rowcount if cur.rowcount >= 0 else 0,
                "last_insert_rowid": None}}})
        conn.commit(); conn.close()
        results.append({"type": "ok", "response": {"type": "close"}})
        payload = json.dumps({"baton": None, "base_url": None, "results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *a): pass

def main():
    db = os.path.join(tempfile.mkdtemp(), "stub.db")
    Stub.db_path = db
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = TursoHTTPStore(f"http://127.0.0.1:{srv.server_port}", TOKEN)
    assert s.watermark() == 0
    ups = [
        {"serial": 1, "payload": {"ops": [{"item": "i-1", "field": "title", "value": "A", "stamp": {"hlc": 1, "device": "d"}}]}, "info": "Added an item"},
        {"serial": 2, "payload": {"ops": [{"item": "i-1", "field": "done", "value": "true", "stamp": {"hlc": 2, "device": "d"}}]}, "info": "Checked off an item"},
    ]
    assert s.apply_updates(ups) == 2
    assert s.watermark() == 2
    assert s.apply_updates(ups) == 0, "re-apply idempotent"
    assert s.count() == 2
    assert [u[0] for u in s.ops_since(1)] == [2]
    assert s.ops_since(0)[0][1]["ops"][0]["stamp"] == {"hlc": 1, "device": "d"}
    # protocol shape spot-checks
    first = shapes[0]["requests"]
    assert all("type" in r for r in first) and shapes[0]["requests"][-1]["type"] == "close"
    insert_req = [b for b in shapes if any(r.get("stmt", {}).get("sql", "").startswith("INSERT OR IGNORE") for r in b["requests"])][0]
    ins = [r for r in insert_req["requests"] if r.get("stmt", {}).get("sql", "").startswith("INSERT OR IGNORE")][0]
    assert ins["stmt"]["args"][0]["type"] == "integer" and isinstance(ins["stmt"]["args"][0]["value"], str)
    assert ins["stmt"]["args"][1]["type"] == "text"
    srv.shutdown()
    print("PASS test_turso_store (stub-backed; not a real Turso DB)")

if __name__ == "__main__":
    main()
