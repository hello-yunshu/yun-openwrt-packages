# aarch64_generic/

历史根目录 APK feed 中的 `aarch64_generic` 包与索引，不代表 OpenWrt 25.12.6 已完成资格验证。
新 feed 使用 `25.12.6/aarch64_generic/`；可用状态见 [支持矩阵](../docs/SUPPORT.md)。

## 文件

- `packages.adb` — 本架构的包索引（已签名）
- `*.apk` — 包本体（每个都单独签名）

## 当前内容

| 包 | 版本 |
| --- | --- |
| `luci-app-nginx-manager` | 1.8.8-r1 |
| `luci-app-cloudflare-ip` | 2.6.0-r13 |
| `luci-app-upnp-nat-relay` | 1.3.13-r4 |
| `luci-app-openclash` | 0.48.002 |

四个包都是 `PKGARCH:=all`（包元数据 `arch: noarch`），但本目录的 `.apk` 由 aarch64_generic
构建任务单独产出并签名，与 `x86_64/` 下的文件字节不同，不要混用。

旧设备端引用地址（GitHub Pages）：

```
https://hello-yunshu.github.io/yun-openwrt-packages/aarch64_generic/packages.adb
```
