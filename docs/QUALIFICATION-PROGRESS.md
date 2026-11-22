# Unified feed qualification progress

Verified 2026-11-21 (local package/repository tests) and 2026-11-22 (published versioned feed, QEMU device-runtime verification).

Two kinds of evidence live here. The 2026-11-21 section records host-side IPK/APK transactions against local test feeds that used temporary keys. The 2026-11-22 section records the production `https://hello-yunshu.github.io/yun-openwrt-packages/` feed, signed by CI, consumed by a published YunWrt image inside QEMU. The 2026-11-21 Runtime observations used the former Preview package and do not qualify the canonical Stable package; the 2026-11-22 observations do.

## Published versioned feed (2026-11-22)

The feed now publishes every qualified package into `<openwrt-version>/<package-arch>/` with canonical `apk` filenames (`<name>-<version>.apk`, required because the v3 index does not carry filenames) plus `packages.adb`, `SHA256SUMS` and per-package evidence files. Indexes are signed by the CI key; the public key ships in the image at `/etc/apk/keys/yun-feed.rsa.pub`.

| OpenWrt | Architecture | Artifacts |
|---|---|---|
| 25.12.6 | `x86_64` | `luci-app-performance-manager-all-1.0.7-r7.apk`, `rill-runtime-1.5.6-r8.apk`, `rill-runtime-manager-1.0.0-r2.apk`, `luci-app-cloudflare-ip-2.6.2-r28.apk`, `luci-app-nginx-manager-1.8.11-r34.apk`, `luci-app-upnp-nat-relay-1.3.16-r16.apk`, `luci-app-openclash-0.48.002.apk` |

Provenance: feed assembly run [45060083625](https://github.com/hello-yunshu/yun-openwrt-packages/actions/runs/45060083625) published the signed index; image build run [45063071232](https://github.com/hello-yunshu/YunWrt/actions/runs/45063071232) consumed it. PM source is locked to `luci-app-performance-manager@428b526886abda48e949638deb9e341c92bdc2a1`; the Runtime lock stays on the immutable Stable release `v1.5.6-r8` (release id 453531268).

## Device-runtime verification: PM 25.12.6 / x86_64 (2026-11-22)

Environment: the published `YunWrt-x86-64-25.12.6-2026-11-22-ext4-combined-efi.img.gz` booted in QEMU (`q35`, OVMF, TCG) — the reference execution environment for this x86_64 disk-image target. The harness supplied SLIRP networking (`eth1` 10.0.2.15/24, DNS 10.0.2.3) so `apk` could reach the production feed URL that the image ships in `/etc/apk/repositories.d/yun-feed.list`.

Procedure and observations, in one boot:

1. **Pristine state.** `apk list --installed` reports `luci-app-performance-manager-all-1.0.7-r7 x86_64`, `rill-runtime-1.5.6-r8 x86_64` and `rill-runtime-manager-1.0.0-r2 noarch`. `/etc/config/performance-manager` has 45 lines; `/etc/init.d/performance-manager` is enabled; `pgrep` finds the service; `ubus list performance-manager` returns the object; `luci-app-performance-manager.json` is in `/usr/share/luci/menu.d/`; `/usr/bin/rill-runtime` is executable.
2. **Downgrade.** The historical all-in-one `luci-app-performance-manager-all-1.0.3-r1.apk` (GitHub release `v1.0.3`) was fetched over the harness LAN and installed with `apk add --allow-untrusted`. The transaction purged `rill-runtime`, because the 1.0.3 package does not depend on it.
3. **Upgrade.** After `apk update` (`OK: 11564 distinct packages available`, `apk policy` showing `1.0.7-r7` from the feed index), `apk add "luci-app-performance-manager-all=1.0.7-r7"` executed the replace transaction without `--allow-untrusted`:
   ```
   (1/2) Installing rill-runtime (1.5.6-r8)
     Executing rill-runtime-1.5.6-r8.pre-install
     Executing rill-runtime-1.5.6-r8.post-install
   (2/2) Upgrading luci-app-performance-manager-all (1.0.3-r1 -> 1.0.7-r7)
     Executing luci-app-performance-manager-all-1.0.7-r7.post-upgrade
   OK: 216.2 MiB in 497 packages
   ```
   Afterwards the installed version is `1.0.7-r7 x86_64`, the config is 45 lines, the service process is running, `/usr/bin/rill-runtime` is executable again, and `/lib/upgrade/keep.d/performance-manager{,-rill}` survived.

Operational note recorded by this run: plain `apk upgrade` (and a name-only `apk add`) skipped the 1.0.3 install without an error, because that version exists only as a local-file install — no repository carries it, so apk has no upgrade candidate for it. The version-pinned `apk add` performed the identical replace transaction. Users moving between published feed versions are unaffected; this caveat applies only to locally installed files.

Caveats: the runtime evidence is QEMU (TCG) execution of the published image, not physical x86 hardware. The upgrade transaction starts from a locally installed old artifact because the feed only publishes the current version. No ARM/Router device runtime was executed.

## Release and architecture evidence (2026-11-21)

| OpenWrt | Format | Target/package architecture | Results |
|---|---|---|---|
| 24.10.8 | IPK/opkg | ipq40xx/generic, `arm_cortex-a7_neon-vfpv4` | PM 1.0.7-r6 installed through host opkg with dependencies from official 24.10.8 feeds plus the local feed; it installed Runtime Manager and the former Preview package. CFI 2.6.2-r27 installed from a separate local feed without Runtime and pulled only Runtime Manager as its Runtime-related dependency. |
| 25.12.6 | APK/apk-tools | x86/64, `x86_64` | CFI installed without Runtime; PM installed and pulled Runtime Manager and the former Preview package. Signed temporary APK repository was accepted; missing-key install failed closed. |

The 24.10 opkg install transaction used a local feed without enabling mandatory signature checks; separately, host opkg tests verified that a temporary key accepts the signature over `Packages.gz` (the bytes opkg downloads) and rejects a signature over uncompressed `Packages`. The 25.12 APK install used a temporary trusted key, and an install without a key failed closed. Production CI secrets and release signatures were not used in these 2026-11-21 tests; the 2026-11-22 verification above is the one that exercised the production feed.

## Artifacts

Hashes below identify local artifacts from the 2026-11-21 working tree and SDK runs. They are not immutable feed releases. The 2026-11-22 published artifacts are listed in the versioned-feed table above; their SHA-256 values are in each architecture's `SHA256SUMS`.

| OpenWrt / architecture | Package | Version | SHA-256 |
|---|---|---|---|
| 24.10.8 / armv7 | `luci-app-cloudflare-ip` | 2.6.2-r27 | `e5ff1236f570d774fb88be69f1803559079afa69628255f0fd6ce049ddde83a0` |
| 24.10.8 / armv7 | `luci-app-performance-manager-all` | 1.0.7-r6 | `97513d0629186a059193c1deea71cc5d2e79a487d974486a2092bc214bde9513` |
| 24.10.8 / armv7 | `rill-runtime-manager` | 1.0.0-r1 | `0e74401f754a0cb3acefd9c62fd43f1e65fbe13bfff6e8022ca5d383be400ea4` |
| 24.10.8 / armv7 | legacy `rill-runtime-preview` test artifact | 1.5.6-r8 | `9413e0aca64d6afd77d498b7f2aea7a9ea57bf936d068c55c4322f6f98fef787` |
| 25.12.6 / x86_64 | `luci-app-cloudflare-ip` | 2.6.2-r27 | `4e61ed32de2e2115e9596c8d2dcd7a86566713a5f684099a8bec201e53fff36c` |
| 25.12.6 / x86_64 | `luci-app-performance-manager-all` | 1.0.7-r6 | `554eed3a9a61b447be31cea3da17b90367dbc6bf58c1a85bdf62990b0abddb3a` |
| 25.12.6 / x86_64 | `rill-runtime-manager` | 1.0.0-r1 | `e9599e910bff5e9be6a8e4bf9fd1c610b95feb70aa694c1c74f150d274a5e91e` |
| 25.12.6 / x86_64 | legacy `rill-runtime-preview` test artifact | 1.5.6-r8 | `2d0b8c2a51e947c86d3180e5f94d308722525ecad746d5486dfd09436c4af4b5` |

The 24.10 ARMv7 Runtime ELF is 32-bit ARM EABI5, hard-float, with `/lib/ld-musl-armhf.so.1`. Runtime execution on ARMv7 hardware was not performed.

The 24.10 PM SDK package target produced an IPK while the SDK invocation used `make -i` to bypass unrelated LuCI SDK dependency failures. The PM IPK itself installed and its dependency graph resolved against release feeds, but this does not count as a clean full-SDK dependency build.

## Qualification state

One matrix cell has reached `device-runtime-qualified`: `luci-app-performance-manager-all` on 25.12.6 / `x86_64`, backed by the QEMU verification above. Its evidence keys record the immutable source commit, the publishing and consuming CI runs, the published artifact hash, the production signature path, the dependency reinstall, the pristine install state, the end-to-end upgrade transaction and the runtime observations.

## Remaining qualification gaps

- Every other matrix cell is still `pending` or explicitly `unsupported`. Those cells carry partial historical observations only; they lack exact-architecture upgrade transactions and immutable published-release evidence.
- Device-runtime evidence exists for the x86_64 disk-image target in QEMU only. No physical x86 hardware and no ARM router devices have been exercised.
- The 24.10 `arm_cortex-a7_neon-vfpv4` cell still depends on the 2026-11-21 local-feed observations and has no published-feed upgrade transaction.
- Source locks for CFI, PM, and Rill Runtime Manager point to immutable pushed commits; the canonical Stable Runtime lock is bound to Rill release `v1.5.6-r8`. The old Preview artifacts remain historical evidence only and are not part of the published feed.
- The remaining feed architectures (24.10.8 IPK targets and the five non-x86_64 APK targets) have built artifacts published but no install/upgrade/runtime verification runs.
