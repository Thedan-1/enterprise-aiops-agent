# Kafka 消费积压排查手册

## 现象
告警 `consumer_lag` 持续上升，订单事件已经进入 Kafka，但库存或通知服务处理明显延迟。生产速率正常不代表消费链路正常。

## 关键指标
- 按 partition 查看 current offset、log end offset 和 lag，不能只看 topic 总量。
- 对比生产速率与消费速率；消费速率长期低于生产速率时积压必然扩大。
- 检查消费者实例数、partition 数、rebalance 次数和单条消息处理耗时。

## 常见根因
消费者下游数据库变慢、单条消息处理发生同步重试、毒消息反复失败、频繁 rebalance，或消费者数量超过 partition 数导致扩容无效。

## 排查顺序
先定位积压 partition，再关联消费者日志和下游依赖延迟。若是毒消息，隔离到死信队列；若是容量不足，先确认 partition 数允许并行度提升再扩消费者。禁止直接跳过 offset，以免造成业务数据丢失。

