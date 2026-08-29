# Kubernetes Pod 频繁重启排查

## 现象
Pod 的 restartCount 持续增加，服务间歇性不可用。先区分 OOMKilled、健康检查失败、进程异常退出和节点驱逐。

## 排查
查看 Pod lastState、exitCode、reason 和 events。OOMKilled 时比较容器 memory working set 与 limit，并检查堆内存、直接内存和 sidecar 占用。Liveness probe 失败时检查探针超时是否小于应用在高负载下的响应时间。

## 风险
盲目提高内存 limit 只能延迟故障；把 liveness probe 放宽过度会让失效实例长期接流量。修复后要观察 restartCount、可用副本数、P95 延迟和错误率是否同时恢复。

