# aarch64_generic/

aarch64_generic 架构的包与索引。

## 文件

- `packages.adb` — 本架构的包索引（已签名）
- `*.apk` — 包本体（每个都单独签名）

## 当前内容

| 包 | 版本 |
| --- | --- |
| `luci-app-nginx-manager` | 1.8.8-r1 |
| `luci-app-cloudflare-ip` | 2.6.0-r13 |
| `luci-app-upnp-nat-relay` | 1.3.13-r4 |

三个包都是 `PKGARCH:=all`（包元数据 `arch: noarch`），因此与 `x86_64/` 下是同一份包文件，
只是索引按架构单独生成。

设备端引用地址（GitHub Pages）：

```
https://hello-yunshu.github.io/yun-openwrt-packages/aarch64_generic/packages.adb
```
