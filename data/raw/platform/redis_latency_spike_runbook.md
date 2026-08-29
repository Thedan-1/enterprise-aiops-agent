# Redis 延迟尖刺诊断 Runbook

## 适用症状

应用 P99 突然升高，Redis 平均延迟仍低；少数请求出现几十到几百毫秒停顿；缓存命中率下降；实例 CPU 未必持续打满。

## 分层定位

必须区分应用端到端延迟、网络往返、Redis 服务端事件和宿主机固有延迟。Redis 返回快不代表应用一定快；连接池等待、DNS、网络和大量串行 round trip 都可能发生在服务端指标之外。

## 排查步骤

1. 对齐应用 trace、客户端连接池等待、Redis command latency 和网络 RTT。
2. 用 `redis-cli --latency` 观察实例往返延迟；在 Redis 宿主机运行 `--intrinsic-latency` 获取系统调度基线。
3. 启用合适阈值的 latency monitor，查看 `LATENCY LATEST`、`HISTORY` 和 `DOCTOR`。
4. 检查 SLOWLOG、大 key、O(N) 命令、Lua 脚本、过期键集中清理和 eviction。
5. 查看持久化事件：fork、AOF rewrite、RDB 保存及磁盘抖动。
6. 比较 Redis 延迟与应用延迟：Redis 正常而应用慢时，检查连接池、网络和命中率下降后的数据库回源。

## 修复与预防

拆分大 key；避免线上执行未评估的 O(N) 命令；批量请求使用 pipeline 降低往返；TTL 加随机抖动；为连接池等待和服务端延迟分别设指标。阈值应来自业务 SLO，而不是统一套用固定毫秒数。

## 参考

基于 Redis 官方 latency monitoring、CLI latency 与 latency diagnosis 文档整理：
https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/
https://redis.io/docs/latest/develop/tools/cli/

