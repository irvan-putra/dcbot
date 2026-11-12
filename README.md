# intodo bot validation (scratch 0.1)

One-off Android test app that checks whether the phone-side bridge bot runtime for
[itdxdc](https://github.com/irvan-putra/intodo) (webxdc ops) works on a real phone,
before anything is integrated into itdapk (the Android app in the same repo).

This is a validation build, not the bot. It runs entirely offline:

- starts the bundled DeltaChat core (deltachat-rpc-server, official chatmail/core 2.69.0
  Android arm64 binary) from the app's native library directory,
- saves and reads back one record in a local SQLite database (stdlib sqlite3 through
  the same OpsStore the bridge bot uses),
- starts and stops an Android foreground service (`specialUse` type),
- writes each result to an on-screen log ending in VALIDATION PASS or FAIL.

It creates no account, connects to no network, and writes nothing outside its own app
folder. Uninstalling removes everything. Package identity is a throwaway
`com.instinct.bottest.scratch`, debug-signed, arm64-v8a only.

Status: built and statically inspected on desktop (APK contents, manifest, ELF
linkage). It has NOT run on a phone yet; installing it is the first real test, and the
load-bearing unknown is whether Android's SELinux policy allows executing the bundled
binary from the native library directory on the target device.

## Build

Needs JDK 17, Android SDK platform 34 + build-tools 34.0.0, and Gradle 8.9
(`sdk.dir` in a gitignored `local.properties`). No wrapper is checked in.

The bundled core binary is NOT in this repo (vendor binary, 21 MB). Fetch the official
artifact and place it at `app/src/main/jniLibs/arm64-v8a/librpcsrv.so`:

- wheel: https://pypi.org/project/deltachat-rpc-server/2.69.0/
  (`deltachat_rpc_server-2.69.0-py3-none-android_21_arm64_v8a.whl`,
  binary inside at `deltachat_rpc_server/deltachat-rpc-server`)
- or the release asset `deltachat-rpc-server-arm64-v8a-android` from
  https://github.com/chatmail/core/releases/tag/v2.69.0

Expected sha256 of `librpcsrv.so`:
`101c7c59675f295efa601eba0e4bcf01fa2456e44b8aa9ed2fa999c6fb995257`

Then: `gradle assembleDebug` -> `app/build/outputs/apk/debug/app-debug.apk`.

## Layout

- `app/src/main/java/.../MainActivity.java` - two buttons (start/stop service) and a log view.
- `app/src/main/java/.../BotService.java` - specialUse foreground service, starts Python (Chaquopy) and runs the validation.
- `app/src/main/python/bot_validation.py` - the offline checks.
- `app/src/main/python/ops_store.py` - the storage adapter under test (stdlib sqlite3 path).
- `app/build.gradle` - AGP 8.5.2 + Chaquopy 17.2.0; `useLegacyPackaging` +
  `android:extractNativeLibs="true"` so the installer extracts the bundled binary as a real file.

## Known limits

- Android 10+ blocks `exec()` from the app data directory; the documented route used
  here is executing a `lib*.so` file extracted from the APK's native library directory
  (Chaquopy issue #605 tracks official support; chaquopy-ffmpeg ships executables this way).
  This must be proven on-device before any integration claim.
- Foreground service behavior under Samsung One UI battery policies is untested; this
  build does not request battery-optimization exemption and does not restart on boot.
- Fallbacks if exec is blocked: JNI bindings (chatmail/core has no published Maven
  artifact, issue #7286) or a targetSdk 28 build (not built; would need an explicit
  decision after risk explanation).
