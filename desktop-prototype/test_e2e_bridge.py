"""Live end-to-end test: webxdc app ops -> bridge bot -> durable storage.

Real DeltaChat core (deltachat-rpc-server), real transport (chatmail relay,
auto-created throwaway profiles - no signup, no personal data), the real
.xdc built from the public repo source, the actual BridgeBot code, and the
libSQL storage adapter. Phases:
  A  bot receives the webxdc instance and persists app updates in order
  B  bot offline -> online catch-up resumes from its watermark
  C  bot publishes an update back into the shared app (restore direction)
"""
import os, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deltachat_rpc_client import DeltaChat, Message, Rpc
from deltachat_rpc_client.const import ViewType
from bot import BridgeBot
from ops_store import OpsStore

CHATMAIL = os.environ.get("CHATMAIL_DOMAIN", "nine.testrun.org")
XDC = os.environ.get("XDC_PATH", "/tmp/xdcbuild/shared-list.xdc")
RPC_SERVER = "/tmp/dcbot/bin/deltachat-rpc-server"
if not os.path.exists(RPC_SERVER):
    RPC_SERVER = "deltachat-rpc-server"

BASE = int(time.time() * 1000)
def stamp(h, device="alice-test"):
    return {"hlc": h, "device": device}

U = [
    {"payload": {"ops": [
        {"item": "i-1", "field": "title", "value": "E2E oat milk", "stamp": stamp(BASE + 1)},
        {"item": "i-1", "field": "done", "value": "false", "stamp": stamp(BASE + 1)}]},
     "info": "Added an item"},
    {"payload": {"ops": [{"item": "i-1", "field": "done", "value": "true", "stamp": stamp(BASE + 2)}]},
     "info": "Checked off an item"},
    {"payload": {"ops": [{"item": "i-1", "field": "deleted", "value": "true", "stamp": stamp(BASE + 3)}]},
     "info": "Removed an item"},
    {"payload": {"ops": [{"item": "i-2", "field": "title", "value": "E2E second", "stamp": stamp(BASE + 4)}]},
     "info": "Added an item"},
]
BOT_PAYLOAD = {"ops": [{"item": "i-2", "field": "note", "value": "from bot storage",
                        "stamp": stamp(BASE + 5, "bridge-bot")}]}

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("[PASS] " if cond else "[FAIL] ") + name, flush=True)

def wait_until(desc, fn, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if fn():
                print(f"[OK] {desc} ({time.time() - t0:.1f}s)", flush=True)
                return
        except Exception:
            pass
        time.sleep(1.5)
    raise TimeoutError(desc)

def main():
    rpc = Rpc(accounts_dir=tempfile.mkdtemp(), rpc_server_path=RPC_SERVER); rpc.start()
    dc = DeltaChat(rpc)
    alice = dc.add_account(); alice.add_transport_from_qr(f"dcaccount:{CHATMAIL}")
    bot = dc.add_account(); bot.add_transport_from_qr(f"dcaccount:{CHATMAIL}")
    check("two chatmail profiles auto-created (no signup flow)", alice.is_configured() and bot.is_configured())
    alice.start_io(); bot.start_io()
    print("[INFO] alice =", alice.get_config("addr"), "| bot =", bot.get_config("addr"), flush=True)

    store = OpsStore(os.path.join(tempfile.mkdtemp(), "ops.db"))
    bridge = BridgeBot(bot, store)
    bridge.run_in_thread()

    contact = alice.create_contact(bot, name="bridge-bot")
    group = alice.create_group("storage-bridge-e2e")
    group.add_contact(contact)
    xdc_msg = group.send_message(text="Shared List", file=XDC, viewtype=ViewType.WEBXDC)
    print("[INFO] .xdc sent, alice-side msg id", xdc_msg.id, flush=True)

    wait_until("bot received and registered the webxdc instance", lambda: len(bridge.instances) == 1)
    bot_inst = next(iter(bridge.instances))
    check("webxdc name matches manifest", bridge.instances[bot_inst].get("name") == "Shared List (prototype)")

    for u in U[:3]:
        xdc_msg.send_webxdc_status_update(u, u["info"])
    wait_until("bot persisted 3 app updates", lambda: store.count() == 3)
    ops = store.ops_since(0)
    check("serials strictly increasing", all(ops[i][0] < ops[i + 1][0] for i in range(len(ops) - 1)))
    check("payloads in order, HLC stamps untouched",
          [o[1]["ops"][0]["value"] for o in ops] == ["E2E oat milk", "true", "true"]
          and ops[0][1]["ops"][0]["stamp"] == {"hlc": BASE + 1, "device": "alice-test"})
    check("info summaries preserved", [o[2] for o in ops] == ["Added an item", "Checked off an item", "Removed an item"])

    n = store.count()
    bridge.process_instance(bot_inst)
    check("idempotent: forced re-process adds nothing", store.count() == n)
    full = Message(bot, bot_inst).get_webxdc_status_updates(0)
    check("full replay from serial 0 returns all 3", len(full) == 3)
    check("full replay apply still idempotent", store.apply_updates(full) == 0 and store.count() == n)

    bot.stop_io(); time.sleep(3)
    xdc_msg.send_webxdc_status_update(U[3], U[3]["info"])
    time.sleep(2)
    bot.start_io()
    wait_until("bot caught up after offline period", lambda: store.count() == 4)
    ops = store.ops_since(0)
    check("watermark resumed correctly (no gap, no dupe)", store.watermark() == ops[-1][0] and len(set(o[0] for o in ops)) == 4)

    bridge.send_update(bot_inst, BOT_PAYLOAD, "Bridge published from storage")
    wait_until("app author sees bot-published update", lambda: len(xdc_msg.get_webxdc_status_updates(0)) == 5)
    alice_all = xdc_msg.get_webxdc_status_updates(0)
    check("bot-published payload visible app-side", alice_all[-1]["payload"]["ops"][0]["value"] == "from bot storage")
    wait_until("bot store ingests its own echo (spec behavior)", lambda: store.count() == 5, 60)

    print("\n== SUMMARY ==", flush=True)
    for name, ok in results:
        print(("PASS" if ok else "FAIL"), "-", name)
    bad = [n for n, ok in results if not ok]
    print("RESULT:", "ALL PASS" if not bad else f"{len(bad)} FAILURES: {bad}", flush=True)
    try:
        dc.stop_io()
    except Exception:
        pass
    os._exit(0 if not bad else 1)

if __name__ == "__main__":
    main()
