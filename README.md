# intodo bot validation (scratch 0.3, r12)

scratch 0.3 keeps the 0.2 OFFLINE probe and adds a LIVE mode: the v6.1
delivery bot running on-device as a foreground service with its own dedicated
chatmail account. Trust model: Delta Chat's contact/invitation flow IS the
boundary - whoever holds the bot's invitation QR can reach it. Any accepted
chat is served with its own isolated list: a group gets a shared list, a
direct chat gets a personal list. There is no owner identity and no
chat-side management; all management and publishing is app-side. The
background model follows the official DeltaChat-Android F-Droid flavor: no
Google push, no third-party servers beyond the chatmail relay.

Buttons (each an explicit tap; nothing runs by itself):
1. Offline validation probe - identical to 0.2, no network.
2. Create bot account - one-time, network: provisions ONE dedicated profile
   on the public chatmail relay via its dcaccount invite. The bot's OWN
   identity, never the user's personal account; the address is shown in the
   app.
3. Start/stop the bot service - permanent-notification foreground service
   (specialUse type, START_STICKY). Stop writes a STOP flag; the python
   watchdog closes the RPC and exits (real stop, single-run lock).
4. Show the invitation QR - SecureJoin setup-contact QR (SVG + text) of the
   RUNNING account, generated on demand by the live loop (INVITE_REQ /
   INVITE_DONE file IPC). The QR text is a bearer invitation: it is never
   logged.
5. Export bot for itdapk - pauses the live bot and writes ONE encrypted
   .dcmig bundle (account backup + bot state) protected by a one-time
   transfer code; see integration/MIGRATION.md.
6. Publish new app version - pick a .xdc; the app stores it under an
   immutable content-addressed name and queues an atomic request
   (PUBLISH_REQ: basename + per-request token). The live loop fans it out
   to every served chat with the v6.1 headline flow (per-chat packed list
   identity, bot-origin registration, full canonical history replay),
   writes a per-chat checkpoint (PUBLISH_PROG) and finally the correlated
   result (PUBLISH_DONE). The UI matches the result to its request by
   token + sha256 and reattaches across activity recreation. A chat that
   misses a publish (added later, revoked at the time, relay failure) is
   healed lazily on its next traffic: the runtime remembers the current
   published version and re-delivers into that chat only - never deleting
   old instances, never downgrading a newer one.

Trust and isolation:
- Contact requests stay refused (core's own boundary).
- Removal: when the core records the bot removed from a chat, access
  pauses; the list id, registrations and store file are kept, and re-adding
  resumes the same list (core chat ids are stable across remove/re-add).
  A revoked chat resumes only on grounded rejoin evidence - a late
  in-flight message alone never revokes the pause.
- Each served chat gets its OWN OpsStore (ops-<id>.db), its OWN stable
  list id and its OWN v6.1 gate/bridge; histories never mix across chats.
- No chat-originated input can publish or administer: the per-chat gates
  are built with no owner address, so their DM command surface refuses
  everyone by construction.
- Network: IMAP/SMTP to the chatmail relay only. No Firebase, no microG.

Build (host: JDK 17, Android SDK 34, gradle 8.9):
    gradle :app:assembleRelease
The APK is arm64-v8a only (the bundled Delta Chat core lib exists for no
other ABI). Native libs ship compressed (legacy packaging,
extractNativeLibs=true); zipalign before signing.

Local JVM tests (Robolectric, no device, no network/core):
    gradle -Pandroid.useAndroidX=true :app:testDebugUnitTest
Covers the publish IPC contract (immutable file, atomic request, DONE
dedup, pending REQ/PROG refusal, recreation reattach) and a native-graphics
render of the initial UI. The python wrapper suite
(app/src/main/python/test_bot_runtime.py) runs the trust/isolation model
against the shipped modules; test_scan_e2e.py (repo root in the task
workspace, not shipped) drives the same membership scenarios against a real
deltachat-rpc-server 2.69.0.
