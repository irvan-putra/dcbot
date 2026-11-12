import json, os, sys, time, traceback

def run(native_dir, files_dir):
    os.environ["OPS_STORE_FORCE_SQLITE"] = "1"
    with open(os.path.join(files_dir, "validation.log"), "w") as log:
        def L(m):
            log.write(time.strftime("%H:%M:%S ") + str(m) + "\n")
            log.flush()
        try:
            L("python " + sys.version.split()[0] + " (chaquopy in-app)")
            server = os.path.join(native_dir, "librpcsrv.so")
            L("bundled server " + server + " exists=" + str(os.path.exists(server)))
            if os.path.exists(server):
                L("mode=%o" % os.stat(server).st_mode)
            from deltachat_rpc_client import Rpc
            rpc = Rpc(accounts_dir=os.path.join(files_dir, "accounts"), rpc_server_path=server)
            rpc.start()
            info = rpc.get_system_info()
            L("core alive: " + json.dumps({k: str(v) for k, v in dict(info).items()})[:400])
            from ops_store import OpsStore
            st = OpsStore(os.path.join(files_dir, "ops.db"))
            fake = [{"serial": 1,
                     "payload": {"ops": [{"item": "i1", "field": "title", "value": "hello",
                                           "stamp": {"hlc": "1@scratch", "device": "scratch"}}]},
                     "info": None}]
            n = st.apply_updates(fake)
            dup = st.apply_updates(fake)
            rows = st.ops_since(0)
            L("sqlite roundtrip: new=%d dup=%d rows=%d wm=%d" % (n, dup, len(rows), st.watermark()))
            ok = n == 1 and dup == 0 and len(rows) == 1 and rows[0][1]["ops"][0]["value"] == "hello"
            try:
                rpc.close()
                L("rpc closed cleanly")
            except Exception:
                L("rpc close raised (non-fatal)")
            L("VALIDATION PASS" if ok else "VALIDATION FAIL: sqlite mismatch")
        except Exception:
            L("VALIDATION FAIL")
            L(traceback.format_exc())
