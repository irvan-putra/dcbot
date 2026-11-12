# Bot migration component: scratch test app -> itdapk (0.4.5)

Moves the EXISTING bot (its Delta Chat identity, served chats,
per-chat list ids and op stores) into the merged itdapk app. No account
reset, no new identity, no reinstall of the Delta Chat side, nothing through
any chat or server: one encrypted file, user-mediated, on one phone.

## User-facing flow

Scratch app (r10):
1. Button "5. Export bot for itdapk" -> confirm dialog (says live bot pauses).
2. Activity stops BotService, waits for the RUNNING lock to clear, runs
   service mode `export`.
3. Python (`migration.export_migration`) generates a one-time transfer code,
   calls core `export_backup(dir, code)` (SQLCipher-encrypted database),
   wraps backup + bot state into `dcbot-migration.dcmig`, writes
   `EXPORT_RESULT` (app-private json: bundle path + code).
4. UI shows the code (selectable, "Copy code" marks the clipboard entry
   IS_SENSITIVE on API 33+), then SAF ACTION_CREATE_DOCUMENT for the bundle.
5. Live bot stays PAUSED. Button 3 = abort and resume. Uninstall only after
   itdapk shows the bot running with the same address.

itdapk (0.4.5):
1. BotActivity first run: "Import bot backup" next to "Create new bot
   account" (import only when no configured account exists - enforced in
   python, refused loudly otherwise).
2. `BotImport` stops BotService, SAF ACTION_OPEN_DOCUMENT, copies the bundle
   to a cache temp file, prompts the transfer code (visible-password field:
   no autocorrect/dictionary), runs `migration.import_migration` on a
   background thread.
3. Success -> callback with the bot address -> UI confirms it matches the
   old app -> only then the first BotService start. Failure -> error shown,
   bundle untouched, nothing committed, retry allowed.
4. After the bot is live in itdapk, the user uninstalls the scratch app
   (its data copy dies with it). Migration complete.

## Bundle format (dcmig/1)

Zip with exactly three members:
- `manifest.json` - format tag, created_at, sha256 + byte size of the two
  ENCRYPTED payloads. No address, no account content.
- `account.backup` - core backup output (tar: SQLCipher-encrypted account
  database + blob files), itself Fernet-wrapped (blobs are not individually
  encrypted by core - this wrap means the bundle has NO plaintext payload).
- `state.bin` - Fernet-encrypted tar.gz of the bot's own state:
  `bot_state.json` (chat registry, per-chat list ids, provisioned flag) +
  `ops-<chat_id>.db` per-chat isolated stores. Excludes logs, invite files
  (bearer QRs), marker files, the accounts dir (carried by the core backup).

Verification order on import: zip structure -> manifest format -> sha256 of
both payloads -> decrypt both (wrong code aborts before ANY write) -> refuse
if an account is already configured -> stage state (member allowlist: flat
safe filenames only, no traversal) -> fresh account + `import_backup` ->
identity check (staged bot_addr must equal the imported account's address)
-> commit state (all-or-nothing, existing files restored on failure) ->
half-imported account removed on any failure. Account keys never leave the
device except inside this encrypted, user-placed file.

## Transfer code (secure UX choice)

32 random bytes, base64url, 44 chars, generated ON-DEVICE at export time.
Handed over same-device: shown once in the exporter UI + copy-to-clipboard
(sensitive-flagged), pasted/typed into the importer. Never logged, never in
the bundle, never through a chat.

One code, three separated uses: SQLCipher passphrase = the code itself
(required by `import_backup`); state key = SHA-256(code|state-domain);
wrap key = SHA-256(code|wrap-domain). The ciphers never share raw material.

Alternatives considered and rejected: persistent password through chat
(chat persistence + shoulder exposure); QR handoff (camera dependency, same
security as clipboard); Android Keystore (per-app, cannot cross packages);
sharedUserId (needs same signing cert - impossible across the two apps);
core `provide_backup`/`get_backup_qr` (iroh P2P transfer: network-dependent,
same-device path unverified, heavier code).

## Builder integration checklist

- Python: add `migration.py` next to the existing `bot_runtime.py` (same
  module names as scratch; `migration` lazily imports `bot_runtime` for
  `_rpc`/`_account_addr`/`save_state`). Keep `ops_store.py`, `turso_store.py`,
  `bot.py`, `delivery_bot.py` in sync with the scratch tree (rev9.1 content).
- Chaquopy pip: `deltachat-rpc-client==2.69.0` AND `cryptography` (Fernet).
- Native: same `librpcsrv.so` pin as scratch
  (sha256 101c7c59675f295efa601eba0e4bcf01fa2456e44b8aa9ed2fa999c6fb995257).
- Kotlin: `integration/BotImport.kt` -> `com.instinct.widget.bot`, call from
  BotActivity; forward `onActivityResult`.
- First-service-start rule: start BotService only after
  `BotImport` reports success (import commits before returning).
- Scratch-side r10: versionCode 6, label "SCRATCH bot 0.3 r10"; the icon
  version badge still reads r9 - needs the r10 redraw (your icon pipeline).
- No raw bot/owner addresses on any public page, repo or release note.

## Grounding

- core v2.69.0 `src/imex.rs`: `export_backup(context, dir, passphrase)` -
  destination is a DIRECTORY, core picks the filename; empty passphrase =
  unencrypted (never used); non-empty encrypts the exported database
  (`export_database`: SQLCipher `ATTACH ... KEY`). `import_backup` restores
  into a fresh account.
- jsonrpc API: `export_backup(account_id, destination, passphrase)` /
  `import_backup(account_id, path, passphrase)` (api.rs ~:1976-2007).
- deltachat-rpc-client 2.69.0: `Account.export_backup(path, passphrase)`,
  `Account.import_backup(path, passphrase)`, `Account.remove()`.
- Account address after QR onboarding/restore: `list_transports()[0]["addr"]`
  (config key "addr" is deprecated/unset - `_account_addr` handles both).

## On-device verification (after both sides land)

1. scratch r10 in-place update (same cert as r9) -> export -> code shown,
   bundle saved via SAF.
2. itdapk 0.4.5 install-over (data survives per 0.4.4 proof) -> import ->
   enter code -> success shows the bot's own address.
3. Bot UI: the bot's own address shown, served chats present.
4. Start service, send a DM to the bot, add it back to the shared group if
   needed; confirm serving. Only then uninstall the scratch app.
5. Negative checks: wrong code -> clean refusal, nothing changed; second
   import attempt after success -> refused (account already configured).
