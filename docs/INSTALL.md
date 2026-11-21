# Device setup

This is the target installation flow for the versioned Yun feed. **Do not use
it until the requested package/release/architecture rows are at least
`build-install-qualified` in [`SUPPORT.md`](SUPPORT.md) and their versioned
indexes have been published.** That level proves package manager and lifecycle
behavior, but does not claim device-side application Runtime behavior. If you
need that claim, require `device-runtime-qualified` for the exact matrix cell.
The existing root-level APK indexes are a legacy feed and are not substitutes
for the qualified 24.10.8 or 25.12.6 paths.

Replace `<package-arch>` with the exact value from `DISTRIB_ARCH` in
`/etc/openwrt_release` (for example `x86_64`, `aarch64_cortex-a53`, or
`mipsel_24kc`).

## OpenWrt 24.10.8 (IPK / opkg)

Install the public key using its usign key ID as the filename. opkg looks up
trusted keys by key ID under `/etc/opkg/keys`.

```sh
set -eu
KEY_ID=e58db45ab792599d
mkdir -p /etc/opkg/keys
wget -O "/etc/opkg/keys/$KEY_ID" \
  "https://raw.githubusercontent.com/hello-yunshu/yun-openwrt-packages/main/keys/yun-openwrt-feed-usign.pub"
printf '%s  %s\n' '0aba6fd7125bc4f66226104e88e7decd288246864c7e47a3751ac8d1030fe714' \
  "/etc/opkg/keys/$KEY_ID" | sha256sum -c -
usign -F -p "/etc/opkg/keys/$KEY_ID"
test "$(usign -F -p "/etc/opkg/keys/$KEY_ID")" = "$KEY_ID"

grep -qE '^[[:space:]]*option[[:space:]]+check_signature[[:space:]]*$' /etc/opkg.conf || \
  echo 'option check_signature' >> /etc/opkg.conf
echo 'src/gz yun-openwrt https://hello-yunshu.github.io/yun-openwrt-packages/24.10.8/<package-arch>/' \
  >> /etc/opkg/customfeeds.conf
opkg update
```

Install CFI with `opkg install luci-app-cloudflare-ip`. PM uses the single
package `luci-app-performance-manager-all`; its hard Runtime dependency is
installed by opkg. Runtime is optional for CFI. Use `opkg upgrade` to update
installed feed packages.

If Stable Rill or a Runtime with unknown package ownership is already present,
PM's hard dependency must not replace it automatically. Resolve the package
conflict after checking ownership and data before installing PM.

## OpenWrt 25.12.6 (APK / apk-tools)

```sh
set -eu
mkdir -p /etc/apk/keys /etc/apk/repositories.d
wget -O /etc/apk/keys/yun-feed.rsa.pub \
  https://raw.githubusercontent.com/hello-yunshu/yun-openwrt-packages/main/keys/yun-feed.rsa.pub
printf '%s  %s\n' '78ca0069e07903f303ff04f598bedd8749e152487735e3b53662864c28591df2' \
  /etc/apk/keys/yun-feed.rsa.pub | sha256sum -c -
echo 'https://hello-yunshu.github.io/yun-openwrt-packages/25.12.6/<package-arch>/packages.adb' \
  > /etc/apk/repositories.d/yun-openwrt.list
apk update
```

Install CFI with `apk add luci-app-cloudflare-ip`. Install PM with
`apk add luci-app-performance-manager-all`; apk resolves its hard Runtime
dependency from the same signed feed. Use `apk upgrade` to update installed
packages.

If Stable Rill or a Runtime with unknown package ownership is already present,
PM's hard dependency must not replace it automatically. Resolve the package
conflict after checking ownership and data before installing PM.

## In LuCI

After installing CFI or PM, use its Runtime panel to inspect the shared
`rill-runtime` Stable package, refresh the configured trusted feed, install it
where supported, or request a guarded update. CFI remains usable in Native mode
when Runtime is missing. PM requires Runtime. Both UIs refuse to replace
unknown-source or incompatible Runtime installations; Runtime updates are
checked against every installed consumer's compatibility manifest.

If the device previously installed `rill-runtime-preview` from the legacy Rill
feed, migrate it through the package manager to the canonical `rill-runtime`
Stable package before using the new Runtime management controls. Remove the old
Rill source entry from opkg/apk after confirming the old package is migrated;
keep its trust key until packages from that feed have been removed. The manager
refuses package actions while competing Runtime feeds are configured, because
the system package manager could otherwise choose either source for the same
package name.

The package manager must be configured with the Yun feed and public key before
those controls can act. They never bootstrap trust by downloading a key from a
device-side button.
