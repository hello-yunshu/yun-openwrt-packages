# keys/

存放本 feed 的**签名公钥**，供设备端校验索引与包。

## 约定

- 文件名必须以 `.rsa.pub` 结尾，apk 才会把它当作公钥加载
- 文件格式为两行：

  ```
  untrusted comment: yun-openwrt-packages signing key
  <public-key.pem 的 base64>
  ```

  第二行是 PEM 公钥整体（含 `-----BEGIN PUBLIC KEY-----`）的 base64，不是裸 DER

## 当前状态

`yun-feed.rsa.pub` 已就位，用于校验本 feed 的索引与包。

公钥指纹（SHA-256）：

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
