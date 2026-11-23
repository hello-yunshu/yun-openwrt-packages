# mosdns 与 luci-app-mosdns：为什么必须验内容才敢发布

## 问题

`mosdns-5.3.4-r15` 这个名字对应**两种互不兼容的构建**：

| | 上游（ImmortalWrt 默认 feed） | 本文采用的构建 |
| --- | --- | --- |
| 二进制大小 | 约 20.0 MB | 约 16.3 MB |
| `stats_api` | 无 | 有 |
| `adblock_set` | 无 | 有 |
| `ip_set` | 无 | 有 |
| `log.size` / `log.backups` | 报 `invalid keys` | 接受 |
| cache prefetch / dump | 无 | 有 |

`luci-app-mosdns` 是按第二种写的。装在第一种上，它不会报错，而是**静默降级**：

- `init.d` 生成的 `/var/etc/mosdns.json` 里含 `log.size` 和 `stats_api`，mosdns 加载即 FATAL，服务起不来；
- 即使绕过生成器改用手写配置，"统计""日志""规则"三个页面也拿不到任何数据——它们依赖 `stats_api` 暴露的 `/plugins/stats_collector/api/v1/*`。

包名、版本号、甚至文件大小都很接近，靠元数据**无法区分**。这正是它能在固件里潜伏很久的原因。

## 采用的来源

```json
"repository": "https://github.com/sbwml/luci-app-mosdns.git",
"path": "mosdns",              // 以及 "luci-app-mosdns"
"ref": "a8a6caffe04167dbb17407a63463eb4ce7243873"
```

该仓库包含 18 个补丁（`100-`、`203-` 至 `219-`），关键几项：

| 补丁 | 作用 |
| --- | --- |
| 207 / 208 / 210 | `adblock_set` 数据库插件、hosts 格式支持、域名匹配 |
| 209 | `log.size` / `log.backups` 日志轮转 |
| 211 | 查询日志 |
| 213 / 214 | cache 主动预取 |
| 216 / 217 / 218 | `stats_api` 统计插件 |

`mosdns/Makefile` 本身不写补丁列表——OpenWrt 构建系统会自动应用 `patches/` 下全部 `*.patch`，所以只要从这个仓库编，补丁一定在。

## 发布范围

两个包都声明 `"releaseSeries": ["25.12"]`，只发布 APK 版本，且只在 `x86_64`、`aarch64_generic` 两个架构上。原因：

- `luci-app-mosdns` 的 `init.d` 与 `mosdns.uc` 按 25.12 的 apk / procd 行为维护；
- sbwml 的 `mosdns/Makefile` 要求 Go 1.25 以上，24.10 的工具链不保证满足；
- 只声明实际维护的两套架构，避免"声明了却从未验证"的假支持。

`build_matrix.py` 现在会尊重 `releaseSeries`（此前只有 `assemble_feed.py` 尊重它，两个脚本口径不一致会导致为不发布的版本白编一遍，并在工具链不足时让整条流水线失败）。

## 门禁

`scripts/verify_mosdns_binary.py` 在发布前解包并**实际运行**候选构建：

1. `stats_api`、`adblock_set`、`ip_set` 与 7 个基础插件必须能注册；
2. 带 `size`/`backups` 的 log 段必须被接受；
3. 起一个真实实例，确认命中 `adblock_set` 规则的查询返回 NXDOMAIN，且该查询被 `stats_api` 计入。

第 3 项的上游指向一个关闭的端口，所以整项检查**不依赖外网**：被拦截的域名不会外发，未拦截的也只会立刻失败，不会真的解析出去。

无法在本机执行的目标架构（跨架构构建）自动降级为静态断言：二进制里必须出现 `stats_api`、`adblock_set`、`ip_set`、`lazy_cache_ttl`、`prefetch` 这些标记。静态检查弱于实跑，但足以拦下"装错了构建"这一种失败——而这正是它要拦的那种。

门禁在 `build.yml` 的 `build-package` 作业内、签名验证之后、上传产物之前执行；失败即中断，坏包不会进入候选 feed。

## 升级

改 `metadata/source-lock.json` 里两个包的 `ref` 到新的上游 commit，并把 `packageVersion` 同步为新的 `PKG_VERSION`。签名与门禁会自动重跑。

若上游引入新的必需插件，`verify_mosdns_binary.py` 的 `REQUIRED_PLUGINS` 要一起更新，否则新能力不会被保护。

## 已知限制

- **i18n 包不在本 feed**：`luci-i18n-mosdns-zh-cn` 仍由上游 feed 提供。翻译是纯文本映射，版本差异不会造成功能问题，但如果上游停止发布，中文界面会退回英文。
- **`geo2txt`、`v2ray-geoip`、`v2ray-geosite` 也不在本 feed**：它们是 `luci-app-mosdns` 的依赖，由 OpenWrt 默认 feed 满足。
- **跨架构只做静态检查**：`aarch64_generic` 的构建没有在真实设备上跑过门禁的第 3 项。
