# Unified feed qualification progress

Verified 2026-11-21. This records local package and repository tests; it does not publish an OpenWrt feed or claim device-runtime qualification. The local Runtime install observations below used the former Preview package and do not qualify the new canonical Stable package.

## Release and architecture evidence

| OpenWrt | Format | Target/package architecture | Results |
|---|---|---|---|
| 24.10.8 | IPK/opkg | ipq40xx/generic, `arm_cortex-a7_neon-vfpv4` | PM 1.0.7-r6 installed through host opkg with dependencies from official 24.10.8 feeds plus the local feed; it installed Runtime Manager and the former Preview package. CFI 2.6.2-r27 installed from a separate local feed without Runtime and pulled only Runtime Manager as its Runtime-related dependency. |
| 25.12.6 | APK/apk-tools | x86/64, `x86_64` | CFI installed without Runtime; PM installed and pulled Runtime Manager and the former Preview package. Signed temporary APK repository was accepted; missing-key install failed closed. |

The 24.10 opkg install transaction used a local feed without enabling mandatory signature checks; separately, host opkg tests verified that a temporary key accepts the signature over `Packages.gz` (the bytes opkg downloads) and rejects a signature over uncompressed `Packages`. The 25.12 APK install used a temporary trusted key, and an install without a key failed closed. Production CI secrets and release signatures were not used.

## Artifacts

Hashes below identify local artifacts from the working tree and SDK runs. They are not immutable feed releases.

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

The 24.10 PM SDK package target produced an IPK while the SDK invocation used `make -i` to bypass unrelated LuCI SDK dependency build failures. The PM IPK itself installed and its dependency graph resolved against release feeds, but this does not count as a clean full-SDK dependency build.

## Remaining qualification gaps

- Matrix rows remain `pending` except explicitly unsupported package/architecture pairs. The selected local rows record partial checks but do not reach `build-install-qualified`: exact architecture upgrade tests and immutable source/release evidence are missing.
- No physical device/runtime test was performed; no build-only result is labeled device-runtime-qualified.
- The 24.10 signature verification used a temporary test key. Production usign trust installation and production index signature are not available locally.
- The 25.12 APK signing/install test used a temporary test key. Production private keys are CI secrets and no release job was executed.
- Source locks for CFI, PM, and Rill Runtime Manager point to immutable pushed commits. The canonical Stable Runtime lock remains pending until its new six-target × two-release qualification is promoted to an immutable Rill release; the old Preview artifacts are historical evidence only.
- The rest of the selected architecture/release matrix has not completed its package build/install/upgrade runs. See `metadata/mainstream-support.json` for per-package entries.
