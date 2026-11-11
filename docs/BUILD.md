# BUILD — 编包 → 签名 → 索引 → 发布

本文件是操作清单，不是教程。带 `[需实测确认]` 的步骤尚未在本机跑通，执行前先小范围验证。

## 0. 前置

- [ ] 架构：`x86_64` 与 `aarch64_generic` 各准备一份 OpenWrt **25.12** SDK
- [ ] 确认 SDK 版本与目标固件一致（同一个 25.12.x，避免 libc / ABI 不匹配）
- [ ] 私钥只在本地或 CI secret 中存在，**不要**放进本仓库

## 1. 取 SDK

- [ ] 下载：`https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/` 下的
      `openwrt-sdk-25.12.6-x86-64_*.tar.zst`，`aarch64_generic` 换成 `armsr/armv8` 对应目录 `[需实测确认：确切文件名]`
- [ ] 校验 `sha256sums` 与下载页公布值一致
- [ ] 解压后进入 SDK 根目录

## 2. 配 feeds

- [ ] `feeds.conf` 增加依赖来源（自研包依赖的 `nginx`、`acme`、`miniupnpc` 等在此源中）：

      ```sh
      echo 'src-git add https://github.com/QiuSimons/OpenWrt-Add.git' >> feeds.conf
      ./scripts/feeds update -a
      ./scripts/feeds install -a
      ```

- [ ] 注意：`acme` 在 25.12 不再是独立包，由 `acme-acmesh` 通过 `PROVIDES:=@acme` 提供，
      `DEPENDS:=+acme` 可以被正常满足，**不需要**改 Makefile

## 3. 放入包源码

- [ ] 把三个包仓库的 `Makefile` 所在目录整体拷进 SDK 的 `package/` 下，例如：

      ```sh
      cp -r /path/to/luci-app-nginx-manager           package/
      cp -r /path/to/luci-app-cloudflare-ip/package/* package/
      cp -r /path/to/luci-app-upnp-nat-relay/package/* package/
      ```

- [ ] 确认目录层级正确：`package/<包名>/Makefile` 必须直接存在，多套一层会找不到包

## 4. 签名密钥

- [ ] 生成 EC P-256 密钥（与 OpenWrt ImageBuilder 保持一致）：

      ```sh
      openssl ecparam -name prime256v1 -genkey -noout -out private-key.pem
      openssl ec -in private-key.pem -pubout -out public-key.pem
      ```

- [ ] 把 `private-key.pem`、`public-key.pem` 放到 SDK **根目录**（`$(TOPDIR)`）。
      `rules.mk` 中 `BUILD_KEY_APK_SEC=$(TOPDIR)/private-key.pem`、`BUILD_KEY_APK_PUB=$(TOPDIR)/public-key.pem`
- [ ] 打开 `CONFIG_SIGN_EACH_PACKAGE=y`（`.config` 中；该选项 `depends on USE_APK`，默认 y）
- [ ] 备份 `private-key.pem` 到仓库外；丢失后设备端将无法验证新旧包的一致性

## 5. 编译

- [ ] `[需实测确认]` SDK 是否自带 `private-key.pem`；若无则按第 4 步生成

      ```sh
      make package/luci-app-nginx-manager/compile V=s
      make package/luci-app-cloudflare-ip/compile V=s
      make package/luci-app-upnp-nat-relay/compile V=s
      ```

- [ ] 产物落在 `bin/packages/<arch>/<subdir>/*.apk` `[需实测确认：本地 package/ 的 subdir 归属]`
- [ ] 逐个确认是 `.apk` 而不是 `.ipk`：`ls bin/packages/*/*/*.apk`
- [ ] 检查依赖是否被自动带上：`apk info -R <包名>` 或查看包内 `depends` 字段

## 6. 生成索引

- [ ] 把该架构所有 `.apk` 收拢到一个目录
- [ ] 生成并签名索引（命令取自 OpenWrt ImageBuilder）：

      ```sh
      apk mkndx \
        --keys-dir ./keys \
        --sign ./private-key.pem \
        --allow-untrusted \
        --output packages.adb \
        ./*.apk
      ```

- [ ] `[需实测确认]` `--allow-untrusted` 的作用范围：仅跳过对输入包的校验，不影响输出索引的签名
- [ ] 校验索引自身可被公钥验证通过（在干净环境里 `apk update` 试一次）

## 7. 发布

- [ ] 公钥写入 `keys/yun-feed.rsa.pub`，内容为 **PEM**（`-----BEGIN PUBLIC KEY-----`）。
      apk 3.0.7 不认 usign 的两行 `untrusted comment:` 格式，实测会报 `UNTRUSTED signature`
- [ ] 把 `packages.adb` 与 `*.apk` 放到本仓库 `<arch>/` 目录
- [ ] 更新 `src.lock`：记录三个包的上游 commit 与 `PKG_VERSION` / `PKG_RELEASE`
- [ ] `git add` 后检查一遍没有把 `*.pem` / `*.key` 带进来
- [ ] 推送后等 GitHub Pages 生效（从 `main` 根目录发布，`.nojekyll` 必须在）

## 8. 版本递增规则

设备端 `apk upgrade` 只有在版本串变化时才认出新包：

- 改代码、依赖、安装文件 → `PKG_RELEASE` +1
- 改上游版本 → 改 `PKG_VERSION`，`PKG_RELEASE` 归 1
- 只改本仓库文档 / 补丁注释 → 不需要动版本

## 9. 失败排查顺序

1. `apk update` 报 `UNTRUSTED signature` → 公钥内容不是 PEM，或没放进 `/etc/apk/keys/`
2. `apk update` 报 `BAD signature` → 索引被改过，或签名时用的不是同一把私钥
3. `apk add` 报缺依赖 → 依赖包不在任何已启用源里，先确认 `feeds.conf` 与 `packages.adb` 内容
4. 包能装但 LuCI 里看不到菜单 → 看 `/usr/share/luci/menu.d/*.json` 是否随包安装，清缓存后重登
5. 中文界面不生效 → 翻译文件应落在 `/usr/lib/lua/luci/i18n/`，检查 `.lmo` 的文件名语言段是否为 `zh-cn`
