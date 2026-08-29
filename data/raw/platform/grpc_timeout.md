# gRPC Deadline Exceeded 排查

`DEADLINE_EXCEEDED` 表示调用在客户端 deadline 前未完成。可能是服务处理慢、连接建立慢、下游超时或客户端 deadline 设置过短。

沿 Trace 拆分客户端排队、网络、服务端处理和下游调用耗时。检查 deadline 是否逐跳递减，以及重试是否在同一总预算内。无上限重试会把短暂抖动放大为请求风暴。修复应优先减少慢点并设置总时间预算，而不是无限增加 deadline。

