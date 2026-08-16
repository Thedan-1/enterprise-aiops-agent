# 历史故障复盘：order-service 大量 502

## 故障现象

order-service 在约10分钟内出现大量 502 Bad Gateway，用户下单请求失败率骤增。同期监控显示 order-service 的 Error Rate 上升至接近20%，P95延迟从200ms上升至2秒以上，CPU/Memory本身并未达到瓶颈。

## 排查过程

1. 首先查看 Nginx 日志，发现大量 `upstream prematurely closed connection` 和少量 `upstream timed out`，判断问题出在 order-service 与其上游/下游之间，而不是 Nginx 自身配置问题
2. 查看 order-service 应用日志，发现连续出现 `connection pool exhausted, waited 5000ms for available connection`，说明数据库连接池被打满
3. 查看 order-service 依赖的 payment-service 当期指标，发现 payment-service 的 P95 延迟同期也有明显上升
4. 进一步排查发现是第三方支付网关当时出现短暂抖动，payment-service 对第三方网关的调用变慢，又因为配置的是无退避的同步重试，进一步放大了payment-service自身的延迟
5. order-service 在创建订单流程中同步调用 payment-service，payment-service变慢导致order-service处理订单请求的耗时被拉长，请求在数据库连接持有期间堆积，最终打满order-service自身的数据库连接池
6. 连接池打满后，新请求无法及时获得数据库连接，处理超时，Nginx因为长时间收不到响应或连接被应用侧主动中断，对外表现为502

## 根因结论

根因不在 order-service 本身，而是"第三方支付网关抖动 → payment-service 同步重试放大延迟 → order-service 同步调用被拖慢 → order-service 数据库连接池耗尽 → Nginx层502"这样一条级联故障链路。order-service 缺少对 payment-service 调用的超时熔断，是导致故障被放大的关键因素。

## 修复措施

- 短期：扩容order-service数据库连接池，重启清空堆积连接，故障缓解
- 长期：为 order-service 对 payment-service 的调用增加熔断器；payment-service 对第三方网关的重试改为指数退避

## 这个案例的价值

这是级联故障（cascading failure）的典型样本：症状出现在order-service（502），根因在两跳之外的第三方支付网关。排查时如果只盯着order-service自身的CPU/Memory（本身并不高），会误判方向；必须顺着调用链路往下游查。
