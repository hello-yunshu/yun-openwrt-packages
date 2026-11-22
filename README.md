# yun-openwrt-packages

目标是统一提供 OpenWrt **24.10.8/IPK** 与 **25.12.6/APK** 软件源，按版本和 package architecture
分别生成受签名保护的索引。目录与资格状态以 [支持矩阵](docs/SUPPORT.md) 和
[`metadata/mainstream-support.json`](metadata/mainstream-support.json) 为准。

```
https://hello-yunshu.github.io/yun-openwrt-packages/<openwrt-version>/<package-arch>/
```

> **当前工作区状态：** 新版本 × 架构资格矩阵尚未完成，不能把下面已有的根目录 APK 索引当作
> 24.10.8 或 25.12.6 的正式支持。通过完整构建、签名、依赖、安装、升级和运行检查后，才会把
> 对应目录标记为可用。24.10.8 处于 OpenWrt old stable；25.12.6 是核验日的 current stable。

仓库最初为 SWrt / YunWrt 固件构建注入而建。根目录下的 `x86_64/` 与 `aarch64_generic/`
索引是既有 25.12 feed 的兼容遗留内容，下面有关这两份索引的操作说明只适用于旧路径。

## 既有根目录 APK feed 中的包（兼容遗留）

| 包名 | 版本 | 架构 | 用途 | 上游 | 许可 |
| --- | --- | --- | --- | --- | --- |
| `luci-app-nginx-manager` | 1.8.8-r1 | noarch | nginx 图形化管理：站点、反向代理、证书、日志、配置测试、备份回滚 | [hello-yunshu/luci-app-nginx-manager](https://github.com/hello-yunshu/luci-app-nginx-manager) | AGPL-3.0-only |
| `luci-app-cloudflare-ip` | 2.6.0-r13 | noarch | Cloudflare IP 优选，并把结果写入 PassWall / OpenClash 配置 | [hello-yunshu/luci-app-cloudflare-ip](https://github.com/hello-yunshu/luci-app-cloudflare-ip) | GPL-3.0 |
| `luci-app-upnp-nat-relay` | 1.3.13-r4 | noarch | 把下游路由器的 UPnP 映射经上游 NAT 中继（nftables DNAT） | [hello-yunshu/luci-app-upnp-nat-relay](https://github.com/hello-yunshu/luci-app-upnp-nat-relay) | GPL-3.0 |
| `luci-app-openclash` | 0.48.002 | noarch | OpenClash 的 LuCI 界面（第三方包，Clash / mihomo 透明代理） | [vernesong/OpenClash](https://github.com/vernesong/OpenClash) | MIT |

`x86_64/` 与 `aarch64_generic/` 两个目录各有一套签名索引和包文件。四个包都是 `PKGARCH:=all`
（包内元数据 `arch: noarch`），但两个架构的 `.apk` 是分别构建、分别签名的，**字节并不相同**；
请只使用与设备架构对应的目录，不要跨目录拷贝。

该旧 feed 尚未包含本轮目标包；新 feed 需要在资格验证后纳入：

- `luci-app-performance-manager-all`：PM 唯一公开安装包，依赖独立发布的 `rill-runtime` Stable。
- `rill-runtime`：PM 的硬依赖、CFI 的可选能力；从 Rill 仓库导入经资格验证的 Stable 产物，不在 feed 内重新编译。
- `luci-app-cloudflare-ip-rill`：历史兼容薄封装，不属于本轮统一 feed 的安装入口。

## 在设备上启用

前提：OpenWrt 25.12，`apk` 命令可用。第三方源必须导入公钥，否则会报 `UNTRUSTED signature`。

```sh
# 1. 导入本 feed 公钥（内容是 PEM，扩展名不影响校验）
mkdir -p /etc/apk/keys
wget -O /etc/apk/keys/yun-feed.rsa.pub \
  https://raw.githubusercontent.com/hello-yunshu/yun-openwrt-packages/main/keys/yun-feed.rsa.pub

# 2. 添加软件源，直接指向 packages.adb
#    地址含 OpenWrt 版本目录（25.12.6 示例）；ARM 设备把末段换成 aarch64_generic
#    根目录旧 flat 索引已随统一 feed 发布下线，不再提供
mkdir -p /etc/apk/repositories.d
echo "https://hello-yunshu.github.io/yun-openwrt-packages/25.12.6/x86_64/packages.adb" \
  > /etc/apk/repositories.d/yun-feed.list

# 3. 刷新索引并安装
apk update
apk add luci-app-nginx-manager
```

说明：

- 源地址必须写到 `packages.adb` 文件本身。只写到目录时，apk 3 会再拼一次 `<arch>/`，结果 404。
- 新增源后必须执行一次 `apk update`，否则 `apk add` 找不到包。
- 本 feed 只提供上表中的包；`luci-base`、`nginx`、`miniupnpc`、`acme*`、`curl`、`jq`、`flock`、
  `kmod-*` 等依赖来自官方 25.12 feeds，不在这里重复分发。官方源不可用时安装会失败。
- 升级用 `apk upgrade`，是否识别新版本取决于 `PKG_VERSION` / `PKG_RELEASE` 是否变化。
- 安装后 LuCI 菜单未出现时，清 `/tmp/luci-indexcache.*` 后重新登录。
- 启动脚本：`/etc/init.d/nginx_manager`、`/etc/init.d/cf_ip`、`/etc/init.d/cf_ip_publisher`
  （仅启用 LAN Publisher 时使用）、`/etc/init.d/upnp_nat_relay`、`/etc/init.d/openclash`。

## 各包的依赖与要求

依赖以下方 `packages.adb` 中的实际元数据为准。

### luci-app-nginx-manager

依赖：`luci-base`、`nginx`、`rpcd`、`rpcd-mod-file`、`openssl-util`、`acme`、
`acme-acmesh-dnsapi`、`diffutils`、`flock`、`libc`。

- 需要设备上运行 nginx；只有 uhttpd 的固件需要先安装 nginx。
- 若固件的 uhttpd 已占用 80/443，需要调整其中一方的监听端口。
- 证书功能依赖 `acme` / `acme-acmesh-dnsapi`，签发时还需要对应的 DNS API 凭据。

### luci-app-cloudflare-ip

依赖：`luci-base`、`bash`、`flock`、`curl`、`tar`、`jq`、`ca-bundle`、`ca-certificates`、`libc`。

- 无内核模块要求。
- 写入 PassWall / OpenClash 配置是可选功能，这两个包不会被自动安装。
- LAN Result Publisher 是可选功能，运行时需要 `uhttpd`；未安装时该功能会失败并报告缺少运行时，
  不影响主流程。

### luci-app-upnp-nat-relay

依赖：`luci-base`、`miniupnpc`、`nftables`、`coreutils-timeout`、`flock`、`libc`。

- 需要 nftables（firewall4）。iptables/firewall3 固件不适用。
- 下游路由器需要启用 UPnP（IGD），否则没有可中继的映射。
- Makefile 声明 `CONFLICTS:=luci-app-upnp-bridge-relay`，两者互斥，安装前请先卸载旧包。
  注意：当前 `.apk` 元数据中没有携带冲突字段，apk 不会自动拦截，必须手动确认。

### luci-app-openclash

依赖：`dnsmasq-full`、`bash`、`curl`、`ca-bundle`、`ip-full`、`ruby`、`ruby-yaml`、
`kmod-tun`、`unzip`、`libc`。

- 上游还要求 `luci`、`luci-base`、`luci-compat`、`kmod-inet-diag`；nftables（firewall4）固件还需要
  `kmod-nft-tproxy`，firewall3 固件则是 `iptables`、`iptables-mod-tproxy`、`iptables-mod-extra`、`ipset`。
  当前 `.apk` 元数据只声明了上面列出的 10 项依赖，这些都没有包含；直接 `apk add` 时请按上游安装命令补装，
  尤其是 `luci-compat`，缺失时 Lua 控制器和界面不会加载。
- `kmod-tun` 必须与设备内核 ABI 匹配，由官方 feed 提供；固件未带该模块且无法安装时，包会装不上或无法启动。
- `dnsmasq-full` 会替换固件自带的 `dnsmasq`，安装前确认可以接受该替换。
- 上游给出的 nftables 安装依赖是：`bash dnsmasq-full curl ca-bundle ip-full ruby ruby-yaml kmod-tun
  kmod-inet-diag unzip kmod-nft-tproxy luci-compat luci luci-base`。
- 安装体积约 23 MB，明显大于其他三个包。
- 这是第三方包，版本与行为跟随上游，问题优先反馈给 OpenClash 项目。

## 构建版本化候选 feed

`.github/workflows/build.yml` 现在是自动链路：

- **触发**：每 6 小时 `schedule`；上游 release 可发 `repository_dispatch`（`upstream-release`）；
  仍保留手动 `workflow_dispatch`。
- **跟踪全部 feed 包**：Nginx Manager、Cloudflare IP、UPnP NAT Relay、Performance Manager All、
  OpenClash，以及 Rill Runtime 和 Rill Runtime Manager。`scripts/update_source_lock.py` 解析每个上游
  最新的正式 Release（非 draft、非 prerelease），固定 tag 对应的 commit、`PKG_VERSION`，以及 Rill 的
  `qualification.json` / `SHA256SUMS` 哈希；有变化时自动提交 `metadata/source-lock.json`。
  新增包只需在 `metadata/mainstream-support.json` 的 `packages` 中加一条声明
  （`repository` + `path` + `architectures`）；调度运行会自动补全并锁定对应的
  `metadata/source-lock.json` 条目，缺失的资格矩阵单元格按包声明的架构自动派生为
  `pending` 或 `unsupported`，无需改脚本、手写 lock 模板或资格行。
- **构建与发布**：自动运行使用 `all-required` 全矩阵。同一 run 内每个产物通过 digest、sourceRef、
  版本和签名核对后记为 `build-verified`；所有适用单元格都达到 `build-verified` 时，候选即为
  `publishable-candidate` 并自动部署到 GitHub Pages。`build-verified` 只声明构建与签名身份，
  不声称安装、升级或设备运行；后两者仍分别需要 `build-install-qualified` 与
  `device-runtime-qualified`。

手动 dispatch 可把 `publish` 设为 `false` 做一次不部署的完整演练；`available-only` 仍可用于只构建
已锁定的包。每个已锁源码还锁了包内 `PKG_VERSION`；CI 同时核对 checkout 的 Makefile、产物文件名和
build evidence，组装器会再次核对 evidence 的 sourceRef 是否等于锁定 commit，避免候选混入其他已构建包
或不同版本。待锁源的提交、资格运行、Rill release asset 哈希和解锁顺序见
[`docs/LOCK-PROMOTION.md`](docs/LOCK-PROMOTION.md)。

工作流按支持矩阵使用对应版本的 SDK 归档构建，统一写入 `<OpenWrt版本>/<package architecture>/`，
并分别生成已签名的 opkg `Packages` 索引和 apk `packages.adb` 索引。自动运行只有在候选包矩阵完整、
每个适用单元格至少达到 `build-verified` 时才部署；不满足时仍会产出可下载审阅的候选，但不会覆盖线上 feed。

历史根目录 APK feed 的手工操作见 [docs/BUILD.md](docs/BUILD.md)，它仍使用旧的 25.12.0 两架构路径，不是本轮版本化构建流程。

### 历史根目录 APK feed 构建步骤

以下仅用于维护既有根目录 APK feed，SDK 标签固定为 `ghcr.io/openwrt/sdk:<arch>-v25.12.0`。

```sh
# 1. 启动 SDK
docker run --rm -it --user root ghcr.io/openwrt/sdk:x86_64-v25.12.0

# 2. 更新 feeds 并安装 LuCI 宿主依赖
cd /builder
git config --global http.version HTTP/1.1
./scripts/feeds update base packages luci
./scripts/feeds install luci-base

# 3. 放入对应 commit 的包源码（路径与 CI 矩阵一致）
#    nginx-manager:        <repo>/.
#    cloudflare-ip:        <repo>/package/luci-app-cloudflare-ip
#    upnp-nat-relay:       <repo>/package/luci-app-upnp-nat-relay
#    openclash:            <repo>/luci-app-openclash
cp -a /path/to/luci-app-nginx-manager/. package/luci-app-nginx-manager/

# 4. 让 25.12 SDK 在打包时逐个签名
python3 - <<'PY'
import pathlib
p = pathlib.Path('include/package-pack.mk')
s = p.read_text()
needle = '\t  --files "$$(IDIR_$(1))" \\\n'
assert needle in s, 'mkpkg --files line not found'
s = s.replace(needle, needle + '\t  --sign "$(TOPDIR)/private-key.pem" \\\n', 1)
p.write_text(s)
PY
cp /path/to/private-key.pem /builder/private-key.pem && chmod 600 /builder/private-key.pem
mkdir -p /builder/keys
cp /path/to/yun-openwrt-packages/keys/yun-feed.rsa.pub /builder/keys/

# 5. 编宿主工具和包
make package/feeds/luci/luci-base/host/compile V=s -j"$(nproc)" </dev/null
echo 'CONFIG_PACKAGE_luci-app-nginx-manager=y' >> .config
make defconfig </dev/null
make package/luci-app-nginx-manager/compile V=s -j"$(nproc)" </dev/null

# 6. 校验签名并重建索引（先清掉目录里的旧版本，避免索引收录过期包）
APK=staging_dir/host/bin/apk
find bin/packages -name '*.apk' -exec "$APK" --keys-dir keys verify {} \;
"$APK" mkndx --allow-untrusted --keys-dir keys \
  --sign-key private-key.pem \
  --output packages.adb $(find bin/packages -name '*.apk')
```

签名与索引的注意事项：

- 私钥不入库，只放在构建机或 CI secret 中；`.gitignore` 已忽略 `*.key` / `*.pem`。
- 公钥必须是 PEM（`-----BEGIN PUBLIC KEY-----`），usign 两行格式会被判 `UNTRUSTED signature`。
- 索引也要签名；`--allow-untrusted` 只跳过输入包校验，不跳过索引签名。
- 产物是 `.apk`，不是 `.ipk`；apk v3 包不能用 `tar -tf` 读取，用 `apk adbdump` 检查内容。
- 发布前更新 `src.lock`，并把 `packages.adb` 与 `.apk` 放进对应架构目录。

## 校验签名

公钥指纹（SHA-256，DER SubjectPublicKeyInfo）：

```sh
openssl pkey -pubin -in keys/yun-feed.rsa.pub -outform DER | openssl dgst -sha256
```

当前值：

```
034b7366bb288d13e0fa9f1b5d6d93c4883be492213a1bcb3e6eeb8402a1a550
```

公钥是 EC P-256；文件名保留 `.rsa.pub` 只是为了和 `/etc/apk/keys/` 的命名习惯一致。

单个包：

```sh
apk verify ./luci-app-nginx-manager-*.apk
```

退出码 0 表示签名有效且由 `/etc/apk/keys/` 中的公钥签发。`BAD signature` 表示内容被改动；
`UNTRUSTED signature` 表示签名有效但签发公钥不在设备信任列表中。

索引：`apk update` 会校验 `packages.adb` 的签名，失败时拒绝使用，不会静默降级。

## 目录结构

```
.
├── LICENSE               # GPL-3.0 全文（本仓库脚本/文档）
├── README.md
├── .nojekyll             # GitHub Pages 关闭 Jekyll
├── keys/                 # 签名公钥，设备端放进 /etc/apk/keys/
├── x86_64/               # packages.adb + *.apk
├── aarch64_generic/      # packages.adb + *.apk
├── patches/              # 对上游包的补丁，按 <包名>/0001-*.patch 组织（当前为空）
├── src.lock              # 自研包的来源 commit 与版本锁定
├── docs/
│   └── BUILD.md          # 编包 → 签名 → 索引 → 发布
└── .github/workflows/
    └── build.yml         # 按包 × 架构矩阵构建并发布
```

## 版本与锁定

- 版本化 feed 的源仓库与 40 位 commit SHA 记录在 `metadata/source-lock.json`；Rill Runtime 另锁不可变 Release ID、
  qualification.json 与 SHA256SUMS 的 SHA256，并验证 release asset 与 qualification evidence 一致。
- `src.lock` 与 `.github/workflows/build.yml` 旧 matrix 的两架构条目只用于根目录历史 APK feed。
- 改代码、依赖或安装文件时 `PKG_RELEASE` +1；改上游版本时改 `PKG_VERSION` 并把 `PKG_RELEASE` 归 1。

## 历史根目录 APK 索引地址

| 架构 | 索引 URL |
| --- | --- |
| `x86_64` | `https://hello-yunshu.github.io/yun-openwrt-packages/x86_64/packages.adb` |
| `aarch64_generic` | `https://hello-yunshu.github.io/yun-openwrt-packages/aarch64_generic/packages.adb` |

## 许可

- 本仓库的脚本、工作流和文档：GPL-3.0，全文见 [LICENSE](LICENSE)。
- `patches/` 下的补丁跟随被修改的上游包许可。
- 仓库内的 `*.apk` 二进制各自遵循上游许可，不因放在本仓库而改变：
  - `luci-app-nginx-manager` — AGPL-3.0-only
  - `luci-app-cloudflare-ip` — GPL-3.0
  - `luci-app-upnp-nat-relay` — GPL-3.0
  - `luci-app-openclash` — MIT
- 分发固件时请自行履行对应许可的源码提供与声明义务。

## 反馈

- 本 feed、签名、索引或构建问题：[GitHub Issues](https://github.com/hello-yunshu/yun-openwrt-packages/issues)
- 包本身的功能问题：优先到对应上游仓库提 issue（见上表链接）。
- 涉及签名私钥或安全问题时，不要在公开 issue 中粘贴私钥或完整密钥文件。

## 相关文档

- [docs/INSTALL.md](docs/INSTALL.md) — 24.10.8/opkg 与 25.12.6/apk 目标配置流程（资格通过后启用）
- [docs/SUPPORT.md](docs/SUPPORT.md) — OpenWrt 版本、主流架构与逐包资格状态
- [docs/BUILD.md](docs/BUILD.md) — 构建、签名、索引、发布与失败排查
- [patches/README.md](patches/README.md) — 补丁目录约定
- [keys/README.md](keys/README.md) — 公钥格式与轮换
