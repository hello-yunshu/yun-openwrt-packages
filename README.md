# yun-openwrt-packages

面向 **OpenWrt 25.12**（apk-tools 3，包格式 `.apk`，索引 `packages.adb`）的私有 APK 软件源。

供给 SWrt / YunWrt 固件在构建时注入，当前收录的是自研 LuCI 应用：

| 包名 | 版本 | 架构 | 说明 |
| --- | --- | --- | --- |
| `luci-app-nginx-manager` | 1.8.8-r1 | noarch | nginx 图形化管理（站点、反代、证书、日志、备份） |
| `luci-app-cloudflare-ip` | 2.6.0-r13 | noarch | Cloudflare IP 优选，并把结果写入 PassWall / OpenClash 配置 |
| `luci-app-upnp-nat-relay` | 1.3.13-r4 | noarch | 下游 UPnP 映射经上游 NAT 中继（nftables DNAT） |

> **当前状态：已发布。** 上表三个包在 `x86_64/` 与 `aarch64_generic/` 两个架构目录里都有签名的
> `packages.adb` 索引，三个 `.apk` 均可用 `keys/yun-feed.rsa.pub` 验证通过。
> 三个包都是 `PKGARCH:=all`（包内元数据为 `arch: noarch`），所以两个架构目录里放的是同一份包文件，
> 索引按架构分别生成。

未收录（有意排除，不是遗漏）：

- `luci-app-performance-manager`：独立的性能管理项目，不在 YunWrt 的 `config_self.seed` 里；
  它的全功能包在构建时需要先把已资格验证的 `rill-runtime` 二进制放进源码树，不属于本 feed 的常规编包路径。
- `rill-runtime` / `rill-runtime-preview`：`luci-app-cloudflare-ip` 的可选依赖，当前设备未启用，不随本 feed 分发。
- `luci-app-cloudflare-ip-rill`：依赖 `rill-runtime-preview` 的薄封装子包，同样未启用。

## 目录结构

```
.
├── LICENSE               # GPL-3.0 全文
├── README.md
├── .gitignore
├── keys/                 # 签名公钥（*.rsa.pub），设备端放进 /etc/apk/keys/
├── x86_64/               # x86_64 架构：packages.adb + *.apk
├── aarch64_generic/      # aarch64_generic 架构：packages.adb + *.apk
├── patches/              # 对上游包的补丁（按 <包名>/0001-*.patch 组织）
├── src.lock              # 上游仓库 commit 与包版本锁定
└── docs/
    └── BUILD.md          # 编包 → 签名 → 索引 → 发布 的操作手册
```

按架构分目录，是为了让设备端只需要引用自己架构的那一个 `packages.adb`，不必在索引里做架构过滤。
`all` 架构（纯脚本、无 ELF 的 LuCI 应用）的包会同时出现在两个架构的索引里。

## 设备端使用

前提：设备是 OpenWrt 25.12（`apk` 命令可用）。安装第三方源需要公钥，否则签名校验会失败并报
`UNTRUSTED signature`。

```sh
# 1. 放入本仓库公钥（内容必须是 PEM，扩展名无所谓；官方 rootfs 用的是 .pem）
mkdir -p /etc/apk/keys
wget -O /etc/apk/keys/yun-feed.rsa.pub \
  https://raw.githubusercontent.com/hello-yunshu/yun-openwrt-packages/main/keys/yun-feed.rsa.pub

# 2. 添加软件源：直接指向 packages.adb，和官方 distfeeds.list 的写法一致
#    x86_64 为例，ARM 设备换成 aarch64_generic
mkdir -p /etc/apk/repositories.d
echo "https://hello-yunshu.github.io/yun-openwrt-packages/x86_64/packages.adb" \
  > /etc/apk/repositories.d/yun-feed.list

# 3. 刷新并安装（三个包可以一起装）
apk update
apk add luci-app-nginx-manager luci-app-cloudflare-ip luci-app-upnp-nat-relay
```

说明：

- 源地址必须写到 `packages.adb` 文件本身。只写到目录时，apk 3 会按 `<目录>/<arch>/` 再拼一次，结果 404。
- `apk update` 只重建本地索引缓存；新增源后必须执行一次，否则 `apk add` 找不到包。
- 依赖（`luci-base`、`nginx`、`miniupnpc`、`acme*`、`curl`、`jq`、`flock` 等）都来自官方
  25.12 feeds，本 feed 只提供自研包本身，不重复分发官方包。
- 若要从本仓库升级，`apk upgrade` 依赖 `PKG_VERSION` / `PKG_RELEASE` 的变化，见 `docs/BUILD.md`。
- 安装后若 LuCI 菜单没出现，清 `/tmp/luci-indexcache.*` 并重新登录；启动脚本分别在
  `/etc/init.d/nginx_manager`、`/etc/init.d/cf_ip`、`/etc/init.d/upnp-nat-relay`。

## 构建端使用

固件构建（ImageBuilder 或 SDK）需要把本 feed 注入，流程是：

```
SDK 编译 → 逐包签名 → apk mkndx 生成索引 → 发布到本仓库对应架构目录
```

细节、确切命令、失败排查见 [docs/BUILD.md](docs/BUILD.md)。要点：

- 编译用 OpenWrt 25.12 SDK，产物是 `.apk`（不是 `.ipk`）。
- 每个 `.apk` 用私钥签名（`apk mkpkg --sign`，等价写法 `--sign-key`），索引也要签（`apk mkndx --sign-key`）。
- 私钥**不入库**，只在构建端或 CI secret 中存在；`.gitignore` 已忽略 `*.key` / `*.pem`。
- 设备端开签名校验时，索引和包都必须能被 `keys/` 里的公钥验证通过，否则整源不可用。

## 许可分层

- 本仓库自身的**脚本、补丁、文档**：GPL-3.0，全文见 [LICENSE](LICENSE)。
- 仓库内的 **`*.apk` 二进制**：各自遵循其上游项目的许可，不因放在本仓库而改变。
  已知来源：
  - `luci-app-nginx-manager` — AGPL-3.0
  - `luci-app-cloudflare-ip` — GPL-3.0
  - `luci-app-upnp-nat-relay` — 上游未声明标准 SPDX 许可（GitHub 显示 NOASSERTION）
- `patches/` 下的补丁若作用于上游代码，其许可跟随被修改的上游包。

分发固件时请自行确认上述许可的合规义务（源码提供、许可声明等）。

## 签名与校验

**公钥指纹**（拿到仓库后先核对，防止中间人替换）：

```sh
openssl pkey -pubin -in keys/yun-feed.rsa.pub -outform DER | openssl dgst -sha256
```

结果与下方指纹比对，一致才继续。

当前公钥指纹（SHA-256）：

```
034b7366bb288d13e0fa9f1b5d6d93c4883be492213a1bcb3e6eeb8402a1a550
```

**单个包是否被替换**：

```sh
apk verify ./luci-app-nginx-manager-*.apk
```

退出码为 0 表示签名有效且由 `keys/` 中某把公钥签发。报 `BAD signature` 表示内容被改动；
报 `UNTRUSTED signature` 表示签名有效但签发公钥不在 `/etc/apk/keys/` 里。

**索引是否被替换**：`apk update` 会校验 `packages.adb` 的签名。索引签名失败时会直接报错并拒绝使用，
不会静默降级。

## 版本与锁定

`src.lock` 记录每个包对应的上游仓库与固定 commit，以及已发布的 `PKG_VERSION` / `PKG_RELEASE`。
CI 矩阵与 `src.lock` 使用同一个 commit，构建可复现。

## 索引地址

| 架构 | 索引 URL |
| --- | --- |
| `x86_64` | `https://hello-yunshu.github.io/yun-openwrt-packages/x86_64/packages.adb` |
| `aarch64_generic` | `https://hello-yunshu.github.io/yun-openwrt-packages/aarch64_generic/packages.adb` |

## 相关文档

- [docs/BUILD.md](docs/BUILD.md) — 构建、签名、索引、发布的操作清单
- [patches/README.md](patches/README.md) — 补丁目录的约定
- [keys/README.md](keys/README.md) — 公钥文件格式与轮换说明
