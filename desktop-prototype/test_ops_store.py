"""Unit test: OpsStore durability semantics, no network."""
import os, tempfile
from ops_store import OpsStore

def main():
    path = os.path.join(tempfile.mkdtemp(), "ops.db")
    s = OpsStore(path)
    assert s.watermark() == 0
    ups = [
        {"serial": 1, "payload": {"ops": [{"item": "i-1", "field": "title", "value": "A", "stamp": {"hlc": 1, "device": "d"}}]}, "info": "Added an item"},
        {"serial": 2, "payload": {"ops": [{"item": "i-1", "field": "done", "value": "true", "stamp": {"hlc": 2, "device": "d"}}]}, "info": "Checked off an item"},
    ]
    assert s.apply_updates(ups) == 2
    assert s.watermark() == 2
    assert s.apply_updates(ups) == 0, "re-apply must be idempotent"
    assert s.count() == 2
    assert [u[0] for u in s.ops_since(1)] == [2]
    assert s.ops_since(0)[0][1]["ops"][0]["stamp"] == {"hlc": 1, "device": "d"}, "payload must round-trip untouched"
    s2 = OpsStore(path)  # reopen: survives "restart"
    assert s2.watermark() == 2 and s2.count() == 2
    print("PASS test_ops_store")

if __name__ == "__main__":
    main()
