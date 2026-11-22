# Legacy BUILD — 根目录 25.12.0 APK feed

本文件只描述已存在的根目录 25.12.0 APK feed 历史构建方式。新版本化构建由
`.github/workflows/build.yml` 负责，来源锁见 `metadata/source-lock.json`，支持边界见 `docs/SUPPORT.md`。
不要用本文件中的两个旧 SDK 架构或根目录索引替代 24.10.8 IPK / 25.12.6 APK 矩阵。

## 0. 前置

- [ ] 架构：`x86_64`、`aarch64_generic` 各一份 25.12 SDK 容器
- [ ] 私钥只在本地或 CI secret 中存在，**不要**放进本仓库
- [ ] 本仓库的 `keys/yun-feed.rsa.pub`（PEM）与私钥配对，指纹见 README

## 1. 取 SDK

- [ ] 直接用官方容器：`docker run --rm -it --user root ghcr.io/openwrt/sdk:x86_64-v25.12.0`
      （`aarch64_generic` 换同名标签；容器里的 SDK 根目录是 `/builder`）
- [ ] 不用官方容器而用 tar 包时，注意 SDK tar **缺 `staging_dir/hostpkg`**：直接编 LuCI 包会从源码拉
      `ucode-mod-html` / `rpcd-mod-luci` / `lucihttp`，然后死在缺头文件上。

## 2. 配 feeds

自研包都是 `PKGARCH:=all`，编译阶段不链接目标库，只依赖 `luci-base` 的宿主工具（`po2lmo`）。

```sh
cd /builder
git config --global http.version HTTP/1.1   # git.openwrt.org 的 TLS 偶发中断，HTTP/1.1 更稳
./scripts/feeds update base packages luci
./scripts/feeds install luci-base
```

- [ ] `package/feeds/luci/luci-base` 符号链接存在，否则下一步的 `host/compile` 会报
      `No rule to make target 'package/feeds/luci/luci-base/host/compile'`
- [ ] 运行时依赖（`nginx`、`miniupnpc`、`acme*`、`curl`、`jq` 等）不需要在这里安装，
      它们由设备端的官方 feed 提供

## 3. 放入包源码

按包放到 `package/<包名>/`，`Makefile` 必须直接在这个目录下：

```sh
cp -a /path/to/luci-app-nginx-manager/.            package/luci-app-nginx-manager/
cp -a /path/to/luci-app-cloudflare-ip/package/luci-app-cloudflare-ip/. package/luci-app-cloudflare-ip/
cp -a /path/to/luci-app-upnp-nat-relay/package/luci-app-upnp-nat-relay/. package/luci-app-upnp-nat-relay/
```

```sh
echo 'CONFIG_PACKAGE_luci-app-nginx-manager=y'   >> .config
echo 'CONFIG_PACKAGE_luci-app-cloudflare-ip=y'   >> .config
make defconfig </dev/null
```

## 4. 签名密钥

25.12 没有 `CONFIG_SIGN_EACH_PACKAGE`，官方 `apk mkpkg` 调用里也不带 `--sign`。
做法是给 `include/package-pack.mk` 打一行补丁，让每个包在打包时签名：

```sh
cp private-key.pem public-key.pem /builder/      # 权限 600，不要入库
python3 - <<'PY'
import pathlib
p = pathlib.Path('include/package-pack.mk')
s = p.read_text()
needle = '\t  --files "$$(IDIR_$(1))" \\\n'
assert needle in s, 'mkpkg --files line not found'
s = s.replace(needle, needle + '\t  --sign "$(TOPDIR)/private-key.pem" \\\n', 1)
p.write_text(s)
PY
```

- [ ] `make package/.../compile` 前完成打补丁，否则产出的包没有签名
- [ ] 私钥放 SDK 根目录（`$(TOPDIR)`），与 `rules.mk` 的 `BUILD_KEY_APK_SEC` 约定一致

## 5. 编译

先编宿主工具，再编包：

```sh
make package/feeds/luci/luci-base/host/compile V=s -j"$(nproc)" </dev/null
test -x staging_dir/hostpkg/bin/po2lmo

make package/luci-app-nginx-manager/compile V=s -j"$(nproc)" </dev/null
make package/luci-app-cloudflare-ip/compile V=s -j"$(nproc)" </dev/null
make package/luci-app-upnp-nat-relay/compile V=s -j"$(nproc)" </dev/null
```

- [ ] 产物在 `bin/packages/<arch>/base/*.apk`（`.apk` 不是 `.ipk`）
- [ ] `po2lmo` 缺失时包的 `Build/Compile` 会跳过 `.lmo`：包能装上但中文界面不生效
- [ ] 用 `apk adbdump --allow-untrusted <pkg>.apk` 检查 `usr/lib/lua/luci/i18n/*.lmo`
      和 `usr/share/luci/menu.d/*.json` 是否在包内（apk v3 包不能用 `tar -tf` 读）

## 6. 校验与索引

```sh
APK=staging_dir/host/bin/apk
$APK --keys-dir keys verify ./*.apk          # 每个包都应输出 OK

$APK mkndx --allow-untrusted --keys-dir keys \
  --sign-key private-key.pem \
  --output packages.adb ./*.apk
```

- [ ] `mkndx` 会把目录里所有 `.apk` 重新索引一遍；**先放齐该架构的全部包再生成**
- [ ] `--allow-untrusted` 只跳过对输入包的校验，索引本身仍然用 `--sign-key` 签名
- [ ] `--sign` 是 `--sign-key` 的旧写法，两者等价

## 7. 发布

- [ ] 公钥必须是 **PEM**（`-----BEGIN PUBLIC KEY-----`）；两行 `untrusted comment:` 格式会被判
      `UNTRUSTED signature`
- [ ] 把 `packages.adb` 与 `*.apk` 放进本仓库 `<arch>/` 目录
- [ ] 更新 `src.lock`：记录上游 commit 与 `PKG_VERSION` / `PKG_RELEASE`
- [ ] `git add` 后检查没有把 `*.pem` / `*.key` 带进来
- [ ] 推送后等 GitHub Pages 生效（从 `main` 根目录发布，`.nojekyll` 必须在）

## 8. 版本递增规则

设备端 `apk upgrade` 只有在版本串变化时才认出新包：

- 改代码、依赖、安装文件 → `PKG_RELEASE` +1
- 改上游版本 → 改 `PKG_VERSION`，`PKG_RELEASE` 归 1
- 只改本仓库文档 / 补丁注释 → 不需要动版本

## 9. 失败排查顺序

1. `apk update` 报 `UNTRUSTED signature` → 公钥内容不是 PEM，或没放进 `/etc/apk/keys/`
2. `apk update` 报 `BAD signature` → 索引被改过，或签名时用的不是同一把私钥
3. `apk update` 报 404 → 源地址写成了目录；必须写到 `packages.adb` 文件本身
4. `apk add` 报缺依赖 → 依赖包不在任何已启用源里，先确认官方 `distfeeds.list` 与 `packages.adb` 内容
5. 包能装但 LuCI 里看不到菜单 → 看 `/usr/share/luci/menu.d/*.json` 是否随包安装，清缓存后重登
6. 中文界面不生效 → 检查包内 `.lmo` 的文件名语言段是否为 `zh-cn`

## 10. 已放弃：自带 QUIC 支持的 nginx 分叉（2026-11-23 记录）

`luci-app-nginx-manager` 的「HTTP/3 ✘ 缺少」来自上游默认值：`net/nginx/Config_ssl.in`
里 `NGINX_HTTP_QUIC` 默认 `n`，所以官方 `nginx-ssl` 不带 `--with-http_v3_module`。
自己编一个 QUIC 版做出完整 drop-in（`PROVIDES:=nginx nginx-ssl`、同版 nginx、同
`--modules-path`）技术上可行，但评估后**主动放弃**：

- 收益：只对浏览器访问路由器 Web UI 生效，局域网链路干净，体验提升接近零。
- 成本：分叉要永久跟两件事——上游 `nginx` 版本（`nginx-mod-ubus` 动态模块按版本校验，
  `--with-compat` 只放宽编译签名不放宽版本）和上游 `patches/nginx/*`（补丁落在
  `auto/*`、`src/event/quic/*`，随 nginx 升版位移）；一旦漏跟，坏的是 LuCI 的 nginx
  入口，故障面远大于少一个 HTTP/3。

若以后重启这条路，先看这五个已经踩过的坑，能省几小时：

1. `PKG_BUILD_DIR` 必须等于 tarball 顶层目录 `nginx-<PKG_VERSION>`，否则解包到隔壁、编译目录为空。
2. SDK 里 `CONFIG_VERSION_NUMBER` 是空的，`include/version.mk` 只被顶层 make 引入；包内要
   `-include $(INCLUDE_DIR)/version.mk` 才能拿到 `VERSION_NUMBER`。
3. nginx 的 `configure` 不是 autotools，SDK 预置的 `--target/--host/--build` 它会直接报错；
   要把 `CONFIGURE_ARGS` 整体替换（上游靠 `201-ignore-invalid-options.patch` 降级成 warning）。
4. 上游 `patches/nginx/` 不是可选的：`101/102/104` 把「运行测试程序」降级成「只编译」（交叉编译
   必需），`103` 补 musl 的 `NGX_SYS_NERR`，`300` 修 OpenSSL 3 下的 QUIC 编译。
5. `make package/<pkg>/compile` 不会装也不会编 feed 依赖；`libopenssl` 会顺带拉
   `cryptodev-linux → kmod → 内核`，代价远大于预期。

重新评估的触发条件：上游把 `Config_ssl.in` 的 `NGINX_HTTP_QUIC` 默认改成 `y`
（届时官方包直接带 HTTP/3，无需本仓库做任何事）。
