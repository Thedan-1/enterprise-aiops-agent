# 服务 DNS 解析失败排查

典型日志包括 `name resolution failed`、`NXDOMAIN` 和 `temporary failure in name resolution`。先确认是单实例、单节点还是全局故障。

检查域名拼写、Service/Endpoint 是否存在、CoreDNS 健康和延迟、节点 `/etc/resolv.conf`、网络策略与 DNS 缓存。若只有新发布版本失败，比较其 namespace 和搜索域配置。不要把 IP 写死作为长期修复，它会破坏服务发现和故障转移。

