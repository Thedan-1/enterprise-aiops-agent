# PostgreSQL 锁等待与阻塞链 Runbook

## 适用症状

接口延迟突然升高但 CPU 不高；数据库活跃会话增加；连接池等待队列增长；SQL 本身平时很快，故障时长时间停在 active；最终可能出现 statement timeout 或连接池耗尽。

## 核心区别

锁等待是事务正在等待另一个事务释放锁；死锁是多个事务形成循环等待。PostgreSQL 能检测死锁并中止其中一个事务，但普通锁等待不会自动等同于死锁。不能看到连接多就直接扩连接池，更多并发事务可能让锁竞争更严重。

## 排查步骤

1. 保存故障时间、接口 request_id、SQL 指纹和事务开始时间。
2. 查询 `pg_stat_activity`，定位长事务、等待事件和空闲在事务中的连接。
3. 结合 `pg_locks` 找出未授予锁以及持有冲突锁的会话，构建 blocker → blocked 阻塞链。
4. 确认阻塞者是在执行、等待客户端，还是 `idle in transaction`。
5. 检查事务是否包含外部 HTTP 调用、批量更新、缺索引扫描或不一致的加锁顺序。
6. 终止会话属于有副作用操作，必须确认业务影响、回滚成本和授权；本 Agent 只提供诊断，不自动执行。

## 修复与预防

缩短事务边界；禁止在事务中等待远程调用；补充合理索引减少扫描范围；统一多表更新顺序；设置 `statement_timeout` 与 `idle_in_transaction_session_timeout`；监控最长事务年龄、锁等待数和连接池等待时间。

## 参考

基于 PostgreSQL 官方 Monitoring Database Activity、`pg_locks` 与 LOCK 文档整理：
https://www.postgresql.org/docs/current/monitoring.html
https://www.postgresql.org/docs/current/monitoring-locks.html

