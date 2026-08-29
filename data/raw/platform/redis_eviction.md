# Redis 内存淘汰异常

`evicted_keys` 持续增长表示 Redis 达到 maxmemory 并按策略淘汰数据。确认 maxmemory-policy、内存碎片率、大 key、TTL 分布和业务命中率。

若缓存数据可重建，可扩容并优化 TTL；若混入不可丢失数据，必须迁移到持久存储。只增加内存而不处理无 TTL key 和大 key 会让问题复发。

