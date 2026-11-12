"""webxdc storage bridge bot.

Runs on the phone (Termux, python + deltachat-rpc-server wheel) on its OWN
DeltaChat profile (chatmail address auto-creates, no signup). Add the bot
profile to the group holding the webxdc app; every status update the app
sends is received here and persisted through a storage adapter.

The bot never sees message contents beyond what the group sees; storage
credentials live only in this process's environment on the phone, never in
the .xdc or the public repo.
"""

import logging
import threading

from deltachat_rpc_client import Bot, Chat, EventType, Message
from deltachat_rpc_client.events import NewMessage, RawEvent

from ops_store import OpsStore

log = logging.getLogger("bridge-bot")


class BridgeBot:
    def __init__(self, account, store: OpsStore):
        self.account = account
        self.store = store
        self.instances = {}  # bot-side msg id -> webxdc info dict
        self.bot = Bot(account, hooks=[
            (self.on_new_message, NewMessage),
            (self.on_status_update, RawEvent(EventType.WEBXDC_STATUS_UPDATE)),
        ])

    def on_new_message(self, event):
        snap = event.message_snapshot
        Chat(self.account, snap.chat_id).accept()  # auto-join chats the bot is added to
        try:
            info = snap.message.get_webxdc_info()
        except Exception:
            return
        if isinstance(info, dict) and info.get("name"):
            self.instances[snap.id] = info
            log.info("webxdc instance registered: msg %s name=%r", snap.id, info.get("name"))

    def on_status_update(self, event):
        self.process_instance(event.msg_id)

    def process_instance(self, msg_id):
        """Fetch updates newer than our watermark and persist them."""
        msg = Message(self.account, msg_id)
        updates = msg.get_webxdc_status_updates(self.store.watermark())
        new = self.store.apply_updates(updates)
        if new:
            log.info("instance %s: persisted %d update(s), watermark=%d", msg_id, new, self.store.watermark())
        return new

    def send_update(self, msg_id, payload, info=""):
        """Publish an update into the shared app (e.g. restore state from storage)."""
        Message(self.account, msg_id).send_webxdc_status_update({"payload": payload, "info": info}, info)

    def run_in_thread(self):
        t = threading.Thread(target=self.bot.run_forever, daemon=True)
        t.start()
        return t


if __name__ == "__main__":
    import os
    from deltachat_rpc_client import DeltaChat, Rpc

    logging.basicConfig(level=logging.INFO)
    rpc = Rpc(accounts_dir=os.environ.get("BOT_ACCOUNTS_DIR", os.path.expanduser("~/.bridge-bot/accounts"))); rpc.start()
    dc = DeltaChat(rpc)
    accounts = dc.get_all_accounts()
    account = accounts[0] if accounts else dc.add_account()
    if not account.is_configured():
        qr = os.environ.get("DCACCOUNT_QR", "dcaccount:nine.testrun.org")
        account.add_transport_from_qr(qr)
    store = OpsStore(os.environ.get("BOT_DB", os.path.expanduser("~/.bridge-bot/ops.db")))
    bridge = BridgeBot(account, store)
    log.info("bridge bot online as %s", account.get_config("addr"))
    bridge.bot.run_forever()
