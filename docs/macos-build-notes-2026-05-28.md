# TrustTunnel macOS — Build & Deployment Notes (2026-05-28)

## Bug: qdarwinpermissionplugin CFBundle Crash (FIXED)

**Symptom:** App crashes on launch with `EXC_BAD_ACCESS (SIGSEGV)` in `CFBundleCopyBundleURL` → `QLibraryInfoPrivate::paths`. Affects both Intel and Apple Silicon.

**Root cause:** PyInstaller extracts to `_MEIPASS` temp dir which is NOT a valid NSBundle. Qt's `CFBundleCopyBundleURL` returns NULL → dereference → segfix.

**Fix:** Migrated from PyInstaller to py2app, which produces a proper `.app` bundle with valid NSBundle structure.

**Verified on:**
- Intel MacBookPro16,3, macOS 15.7.7 (Denis)
- arm64 M1 MacBook-Pro-7 (Vladimir)  
- arm64 M3 Pro MacBook-Pro-Pavel, macOS 26.5 Tahoe (Ferz)

---

## Bug: Universal2 merge fails silently (dist_x86_64 not created)

**Symptom:** `build-app-py2app.sh` x86_64 step prints "Done!" but `dist_x86_64/` directory is never created, leaving `dist/` empty.

**Root cause:** The script does `mkdir -p dist_x86_64` then `mv dist/TrustTunnel.app dist_x86_64/TrustTunnel.app`. If mkdir silently fails (permissions, etc.), the mv fails too.

**Fix:** Always verify `dist_x86_64/` exists before mv:
```bash
mkdir -p dist_x86_64
test -d dist_x86_64 || { echo "FATAL: mkdir dist_x86_64 failed"; exit 1; }
mv dist/TrustTunnel.app dist_x86_64/TrustTunnel.app
```

---

## Bug: setup-sudo.sh doesn't find trusttunnel_client binary

**Symptom:** `setup-sudo.sh` reports "trusttunnel_client not found" even though app is installed.

**Root cause:** Script searches `Contents/Resources/bin/trusttunnel_client` but py2app puts it at `Contents/Resources/trusttunnel_client`.

**Fix:** Update setup-sudo.sh to search both paths:
```bash
for path in     "$APP/Contents/Resources/bin/trusttunnel_client"     "$APP/Contents/Resources/trusttunnel_client"     ...; do
```

---

## Bug: SSH pubkey auth fails with "account is locked" after useradd

**Symptom:** `useradd -m -s /bin/bash ferz` creates account with locked password. sshd rejects with "User ferz not allowed because account is locked".

**Fix:** Unlock after creation:
```bash
usermod -p '*' ferz
# Or: passwd -u ferz (may warn about passwordless)
```

---

## Bug: Multi-user reverse SSH tunnel — AuthorizedKeysFile hardcoded

**Symptom:** Second tunnel user (ferz) gets "Permission denied (publickey)" even with correct key in `~/.ssh/authorized_keys`.

**Root cause:** `sshd_config_tunnel` had `AuthorizedKeysFile /home/denis/.ssh/authorized_keys` (hardcoded to first user).

**Fix:** Use `%h` for home directory:
```bash
AuthorizedKeysFile %h/.ssh/authorized_keys
```

---

## Bug: macOS PAM rejects pubkey auth on tunnel-forwarded connections

**Symptom:** Custom debug sshd on port 2222 successfully reads `authorized_keys` but still rejects the key with "Failed publickey" in debug log.

**Root cause:** Apple macOS OpenSSH 9.9 runs PAM account checks that reject non-interactive localhost connections. `UsePAM no` workaround works for debug sshd but isn't suitable for production.

**Workaround:** Create a dedicated system user without PAM restrictions, or use `UsePAM no` on a custom debug sshd instance.

---

## Network: Double SSH tunnel too slow for large file transfers

**Symptom:** SCP of 100MB+ zip through double tunnel (VPS ↔ Mac ↔ Ferz Mac) consistently times out.

**Workaround:** Use GitHub Releases for distribution. Only scripts/configs should go through direct SCP.

---

## Fixed: install-app.sh download URL

**Symptom:** `curl -L -o /tmp/TrustTunnel.zip https://github.com/.../releases/latest/download/TrustTunnel.zip` returns 44.

**Root cause:** Asset is named `TrustTunnel-macOS-vX.Y.Z.zip`, not `TrustTunnel.zip`.

**Fix:** `install-app.sh` already uses GitHub API to find the correct URL dynamically. No fix needed — it works.
