# OpenWrt release and architecture support

The feed targets the two package formats in current use by this project:

| OpenWrt release | Package format | Package manager | Status at verification |
| --- | --- | --- | --- |
| 24.10.8 | IPK | opkg | Latest published 24.10 release; old stable/outdated, with limited security and bug fixes according to the downloads page |
| 25.12.6 | APK v3 | apk-tools | Current stable release on 2026-11-21 |

OpenWrt's 24.10.8 release announcement projected September 2026 EOL, and a
September 2026 development notice described 24.10.9 as the planned final
release while considering the branch EOL. The official release index still
listed 24.10.8 as the newest published 24.10 build on 2026-11-21; no 24.10.9
release directory was present. Treat 24.10.8 as a compatibility target and
recheck the official index before any future package release.

OpenWrt's official package indexes list 36 package architectures for 24.10 and
35 for 25.12. The Yun feed deliberately starts with seven common architectures,
so each one can receive meaningful install and upgrade qualification rather
than relying on an exhaustive but untested architecture list.

| Package architecture | Representative target/subtarget | CFI and manager | PM and Rill Runtime |
| --- | --- | --- | --- |
| `x86_64` | `x86/64` | 25.12.6: local build/install evidence; qualification pending | 25.12.6: local build/install evidence; qualification pending |
| `aarch64_generic` | `armsr/armv8` | Pending | Pending |
| `aarch64_cortex-a53` | `mediatek/filogic` | Pending | Pending |
| `aarch64_cortex-a72` | `bcm27xx/bcm2711` | Pending | Pending |
| `aarch64_cortex-a76` | `bcm27xx/bcm2712` | Pending | Pending |
| `arm_cortex-a7_neon-vfpv4` | `ipq40xx/generic` | 24.10.8: local build/install evidence; qualification pending | 24.10.8: local build/install evidence; qualification pending |
| `mipsel_24kc` | `ramips/mt7621` | Pending | Not supported yet: Runtime Rust standard library and end-to-end ABI qualification are not in place |

## Qualification levels

Each supported package × release × architecture cell has one explicit level in
[`mainstream-support.json`](../metadata/mainstream-support.json):

| Matrix status | Required evidence | Meaning |
| --- | --- | --- |
| `pending` | None yet | No support claim; do not use as a qualified release target |
| `build-install-qualified` | Build, signature, dependency resolution, clean install, and upgrade evidence | Package manager and package lifecycle work for the target. Device-side application Runtime behavior has **not** been evaluated. |
| `device-runtime-qualified` | Everything above plus device/runtime evidence | The application and native Runtime were exercised on a real device or a validated target runtime. |
| `unsupported` | Exclusion reason | The package is intentionally absent for that version/architecture cell. |

Publishing permits a complete matrix where every supported cell reaches at
least `build-install-qualified`. This level must never be reported as
`device-runtime-qualified`; that requires separate runtime evidence.

CFI and the Runtime Manager are architecture-independent package payloads. The
manager can install or update Rill only where a qualified Runtime package is
published. PM has a hard Runtime dependency, so it is not published to the MIPS
feed until that Runtime architecture is built and qualified.

The machine-readable source of this matrix is
[`../metadata/mainstream-support.json`](../metadata/mainstream-support.json).
The detailed matrix contains 98 package × release × architecture rows: 94
supported cells remain pending and 4 explicitly exclude PM/Rill on MIPS across
the two releases. Two release/architecture combinations now include partial
local artifact, dependency, signature-test, and clean-install evidence. They
remain pending because exact-source immutable release proof, production-key
signature, upgrade, and device-runtime qualification are incomplete. See
[`QUALIFICATION-PROGRESS.md`](QUALIFICATION-PROGRESS.md).

## Evidence

- Official [release index](https://downloads.openwrt.org/releases/) listed
  24.10.8 as the newest published 24.10 release and 25.12.6 as the newest
  current-stable release on the verification date. The official [downloads
  page](https://downloads.openwrt.org/) describes 24.10 as outdated while still
  receiving limited security and bug fixes; the [24.10.8 announcement](https://lists.openwrt.org/pipermail/openwrt-announce/2026-July/000089.html)
  projected September 2026 EOL. A [development notice](https://lists.openwrt.org/pipermail/openwrt-devel/2026-September/045085.html)
  planned 24.10.9 as the final release, but it was not yet listed in the
  official release index on 2026-11-21.
- Official [24.10 package architecture index](https://downloads.openwrt.org/releases/packages-24.10/)
  and [25.12 package architecture index](https://downloads.openwrt.org/releases/packages-25.12/)
  provide the full package architecture inventories.
- Each representative target is cross-checked against the corresponding
  release's `profiles.json` and official SDK archive in its target directory.
- The Rill Runtime target registry is checked against the same six native
  targets for both releases; `mipsel_24kc` remains outside that registry until
  the Rust standard library and runtime ABI can be qualified.
- OpenWrt's branch-specific [`rust-values.mk` for 24.10](https://github.com/openwrt/packages/blob/openwrt-24.10/lang/rust/rust-values.mk)
  and [`rust-values.mk` for 25.12](https://github.com/openwrt/packages/blob/openwrt-25.12/lang/rust/rust-values.mk)
  define target triples used by the native package toolchain. A Rust target
  mapping alone does not count as a successful Runtime build.

The 24.10 feed remains a compatibility target. It is not the current stable
series, and the branch is near or past its announced maintenance window;
deployments should prefer 25.12 where supported. The feed must be rechecked
against the official release index and package/SDK availability before each
release.
