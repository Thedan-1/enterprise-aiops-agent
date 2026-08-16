# order-service 服务文档

## 概述

order-service 是订单核心服务，负责订单创建、查询、状态流转。技术栈：Java 17 + Spring Boot，数据库为 PostgreSQL，通过 HikariCP 管理连接池。

## 依赖关系

order-service 在创建订单时会同步调用：
- payment-service（发起支付预授权）
- inventory-service（扣减库存）

这两个下游服务的可用性和延迟直接影响 order-service 的响应时间——如果 payment-service 或 inventory-service 变慢，order-service 处理请求的耗时会相应变长，进而影响 order-service 自身的连接池和线程池占用。

## 关键接口

### POST /api/orders
创建订单。同步调用 payment-service 和 inventory-service，超时时间各设置为 3 秒。

### GET /api/orders/{id}
查询订单详情，纯数据库读操作，不依赖下游服务。

## 已知风险点

1. order-service 的数据库连接池（HikariCP）默认最大连接数为 20，在大促期间曾出现连接池耗尽的情况
2. 对 payment-service 的调用没有配置熔断器（circuit breaker），当 payment-service 大面积超时时，order-service 会被拖慢甚至雪崩
3. Nginx 面向 order-service 的 `proxy_read_timeout` 配置为 5 秒，短于 order-service 自身对下游的超时总和（payment 3s + inventory 3s = 6s 的极端情况），在下游同时变慢时容易触发网关层 504

## 监控指标

关注 order-service 的：QPS、Error Rate、P95/P99延迟、数据库连接池使用率、JVM GC 频率。
