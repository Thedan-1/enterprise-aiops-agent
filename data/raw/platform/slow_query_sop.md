# 慢查询排查 SOP

先从慢查询日志或 pg_stat_statements 找到总耗时贡献最大的 SQL，而不是只盯单次最慢 SQL。执行 EXPLAIN ANALYZE 时要注意生产风险。

检查全表扫描、估算行数偏差、排序落盘、锁等待和 N+1 查询。索引不是越多越好，它会增加写放大和维护成本。优化后对比执行计划、P95、数据库 CPU、buffer hit ratio 和业务吞吐。

