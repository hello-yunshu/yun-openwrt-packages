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

私钥不在此目录，也不在仓库内；仅存在于构建机与 CI secret 中。

## 轮换

1. 生成新密钥对（EC P-256）
2. 新公钥以新文件名放进本目录，**旧公钥暂时保留**，避免已装机的设备立刻失效
3. 用新私钥重签索引与所有包
4. 等设备端公钥更新完成后再删除旧公钥

## 不要放

- 私钥。`.gitignore` 已忽略 `*.key` / `*.pem`，但不要依赖它兜底
