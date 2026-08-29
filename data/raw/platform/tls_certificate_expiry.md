# TLS 证书过期与握手失败

证书故障常表现为 `certificate has expired`、`unknown authority`、主机名不匹配或 TLS handshake timeout。检查服务端证书有效期、完整证书链、SNI、系统时间和客户端信任库。

证书轮换后要验证所有实例都加载了新证书；只更新文件但未 reload 进程会继续使用旧证书。建立到期前 30/14/7 天告警，并对轮换流程做自动化演练。

