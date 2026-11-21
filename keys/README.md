# keys/

存放本 feed 的**签名公钥**，供设备端校验索引与包。

## 格式（实测结论）

apk-tools 3.0.7 只按 **PEM** 解析公钥文件，文件名后缀它并不关心。
实测对照（同一把 EC P-256 私钥签出的包）：

| 公钥文件内容 | `apk verify` 结果 |
| --- | --- |
| 两行 usign 风格（`untrusted comment:` + base64） | `UNTRUSTED signature` |
| PEM（`-----BEGIN PUBLIC KEY-----`） | `OK` |

因此这里放的是 PEM 公钥；文件名保留 `.rsa.pub` 后缀只是为了和设备上
`/etc/apk/keys/` 的命名习惯一致（OpenWrt 25.12 官方 rootfs 里是
`/etc/apk/keys/openwrt-25.12.pem`，PEM 内容）。

## 当前状态

`yun-feed.rsa.pub` 已就位，用于校验本 feed 的索引与包。

公钥指纹（SHA-256，DER SubjectPublicKeyInfo）：

```
034b7366bb288d13e0fa9f1b5d6d93c4883be492213a1bcb3e6eeb8402a1a550
```

PEM 文件原始字节 SHA-256（供设备端用 `sha256sum -c` 校验首次导入）：

```
78ca0069e07903f303ff04f598bedd8749e152487735e3b53662864c28591df2
```

私钥不在此目录，也不在仓库内；仅存在于构建机与 CI secret 中。

`yun-openwrt-feed-usign.pub` 是 OpenWrt 24.10/opkg 源的 usign 公钥。导入设备时，必须将它保存为
`/etc/opkg/keys/e58db45ab792599d`；opkg 依据 usign key ID 查找信任密钥。密钥 ID：

```
e58db45ab792599d
```

公钥文件原始字节 SHA-256（首次导入时也应校验）：

```
0aba6fd7125bc4f66226104e88e7decd288246864c7e47a3751ac8d1030fe714
```

对应私钥只保存在 `YUN_OPENWRT_IPK_SIGNING_KEY` CI secret。它只签署 IPK feed
索引；APK feed 和 APK 包继续使用上述 `yun-feed.rsa.pub` 对应的 APK 密钥。

## 轮换

1. 生成新密钥对（EC P-256）
2. 新公钥以新文件名放进本目录，**旧公钥暂时保留**，避免已装机的设备立刻失效
3. 用新私钥重签索引与所有包
4. 等设备端公钥更新完成后再删除旧公钥

## 不要放

- 私钥。`.gitignore` 已忽略 `*.key` / `*.pem`，但不要依赖它兜底
