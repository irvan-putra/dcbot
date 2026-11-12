# webxdc storage bridge bot + storage adapter #1 (libSQL/Turso)

Product names (user-chosen, 12 Nov 2026): itdweb = the Instinct hosted page,
itdapk = the Android APK with widget, itdxdc = the webxdc DeltaChat mini-app.
This bot bridges itdxdc (and any webxdc app) to durable storage.

A phone-side DeltaChat bot that persists a webxdc app's updates to durable
storage. The mini-app keeps its no-internet boundary; the bot is a separate
DeltaChat profile in the same group, so it receives every status update the
app sends (webxdc updates go to all chat members) and can publish updates
back (e.g. restore state from storage).

## What is verified (test_e2e_bridge.py, 12 Nov 2026, ALL PASS)

Real deltachat-rpc-server core, real chatmail transport (throwaway
auto-created profiles on nine.testrun.org, no signup, no personal data),
the real itdxdc .xdc built from github.com/irvan-putra/intodo
webxdc/ source, the actual BridgeBot code:

- bot profile joins the group, receives the webxdc instance
- app updates (exact app.js ops schema: item/field/value/stamp{hlc,device})
  arrive at the bot in order and persist with info summaries; HLC stamps
  untouched (MergeDoc replay stays canonical)
- idempotent apply; full replay from serial 0; no gaps/dupes after an
  offline period (watermark resume, same semantics as setUpdateListener(cb,
  serial) - serials are LOCAL to each profile's view)
- bot can send_webxdc_status_update back into the shared app; the app side
  sees it (restore direction works)
- OpsStore passes with libSQL and stdlib sqlite3 backends

## Setup (desktop, CPython 3.10)
pip install -r requirements.txt
Pinned: deltachat-rpc-client==2.69.0, deltachat-rpc-server==2.69.0
(installs the matching prebuilt core), libsql-experimental==0.0.55.
Tests: python test_ops_store.py && python test_turso_store.py (no network);
python test_e2e_bridge.py needs network and XDC_PATH pointing at a built
shared-list .xdc (see test source), and auto-creates throwaway chatmail
profiles.

## Files
- ops_store.py  adapter #1: ops log + watermark, local (libSQL or stdlib sqlite3).
  Byte-identical to the Android validation app's copy at
  app/src/main/python/ops_store.py (sha256
  e73c30e95e6308d5ab2db2a94b5a80a4a194f946c062abb7f263334ab0803b85) - fix bugs in both
- turso_store.py  adapter #1b: same interface over Turso SQL-over-HTTP (stdlib
  urllib, phone-ready). Protocol-tested against a local stub ONLY - never run
  against a real Turso DB (none exists; creating one is the user's decision)
- bot.py        BridgeBot: auto-join, instance tracking, update -> store, send-back
  (bridges itdxdc's ops stream; the same bridge can serve itdapk later)
- test_e2e_bridge.py  live transport test (chatmail throwaway profiles)
- test_ops_store.py / test_turso_store.py  storage semantics, no network

## Verification boundaries (kept deliberately narrow)
VERIFIED: DeltaChat-transport + bot capability on real core over a real
chatmail relay (desktop linux x86_64); local storage on libSQL and sqlite3;
Turso HTTP protocol shaping against a stub.
NOT VERIFIED: anything on the actual phone (Termux run is the first test),
anything against a real cloud database, multi-instance operation, real DeltaChat/
ArcaneChat clients (a user retest with real clients is still pending).

## Test-resource cleanup (done 12 Nov 2026 ~09:41 WIB)
The live test created 6 throwaway chatmail profiles on nine.testrun.org
(2 per run x 3 runs) plus one test group each. Per the relay's official
privacy page (https://nine.testrun.org/privacy.html): no personal data is
asked or retained, messages are unconditionally removed after 20 days, and
profiles carry random addresses with unique random passwords. Accurate record: six external profiles were created; the local credential
copies (per-run temp dirs with accounts DBs and ops DBs) were deleted; the
remote profiles are NOT confirmed deleted - no server-side deletion was
performed and we no longer hold the credentials to do it ourselves. What
remains remotely: random-address profiles whose messages expire under the
operator policy (messages removed unconditionally after 20 days). Local
deletion is not a guarantee of remote removal. No tokens, keys or secrets
were sent anywhere or persisted.

## Phone hosting (Samsung A24, Termux)
- PyPI deltachat-rpc-server 2.69.0 ships an android_21_arm64_v8a wheel
  (official prebuilt core for this exact architecture).
- Termux pip may not accept android platform tags (pypa/pip#13299,
  termux/termux-packages#25150): download the wheel manually
  (pip download --platform android_21_arm64_v8a --only-binary :all: --no-deps
  on any machine, copy over, unzip; the wheel contains a self-contained
  binary, but whether it runs on the phone is UNVERIFIED - the first phone
  run is the test).
- libsql-experimental has NO android/aarch64 wheel: on the phone the adapter
  uses stdlib sqlite3 for the local file (tested). Turso cloud from the phone
  will use Turso's HTTP API (pure HTTPS, no wheel) - next increment.
- Run: BOT_DB=~/.bridge-bot/ops.db python bot.py (DCACCOUNT_QR optional;
  defaults to a fresh chatmail profile). Keep the profile dedicated to the
  bot; back up the accounts dir + ops.db (serials are profile-local).

## Storage ease order (grounded in the storage research + adapter work here)
1. Turso/libSQL - DONE as local ops log; cloud = URL+token (needs Turso DB)
2. Upstash Redis / Supabase PostgREST - pure HTTPS REST, easy drivers, but
   Upstash is a sidecar and Supabase free tier pauses after 1 idle week
3. Neon - serverless Postgres (HTTPS driver), no pause issues
4. Firebase Firestore - Android-native but service-account auth is heavier
5. Cloudflare D1 - needs a Workers API, vendor-specific
6. MongoDB Atlas M0 - durable but 512 MB, native driver needed
7. GitHub encrypted - existing account, but research verdict: mirror/backup,
   not a live DB; token custody decision needed
8. Qdrant - vector search only; Oracle - card required, heavy

## Not done / decisions for the user
- Turso (or any cloud) account + credentials: user's choice; credentials
  stay on the phone, never in the .xdc or the public repo
- on-device Termux run of the rpc-server wheel
- Turso HTTP backend, materialized "current items" view (replay ops through
  canonical MergeDoc), multi-instance storage, encrypted-at-rest ops
- whether the bot joins the real shared-list group
  (code home: this directory, desktop-prototype/ in
  github.com/irvan-putra/intodo-bot-validation)
