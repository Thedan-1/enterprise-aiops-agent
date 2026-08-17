"""模拟历史故障工单。生产环境替换点：接入Jira/内部工单系统API，函数签名不变。"""

_TICKETS = [
    {
        "id": "TICKET-1042", "title": "order-service大量502,订单提交失败",
        "service": "order-service", "status": "resolved",
        "resolution": "根因是payment-service对第三方支付网关的同步重试放大了延迟,导致"
                       "order-service数据库连接池耗尽。修复:为order-service对payment-service"
                       "的调用增加了1s超时+熔断,payment-service对第三方网关的重试改为指数退避。",
        "resolved_at": "2026-06-12",
    },
    {
        "id": "TICKET-987", "title": "inventory-service响应变慢,P95从100ms涨到900ms+",
        "service": "inventory-service", "status": "resolved",
        "resolution": "本地缓存Map无容量上限导致堆内存压力增大,Full GC频繁。修复:替换为带"
                       "LRU淘汰+容量上限的缓存实现,并补充了Memory使用率告警阈值。",
        "resolved_at": "2026-05-03",
    },
    {
        "id": "TICKET-1101", "title": "促销期间Redis连接数耗尽,部分请求报错",
        "service": "redis", "status": "resolved",
        "resolution": "Redis客户端连接池maxTotal配置过小(默认8),促销流量下被打满。修复:"
                       "根据QPS峰值重新计算并调大连接池上限,同时补充连接池使用率监控。",
        "resolved_at": "2026-04-20",
    },
    {
        "id": "TICKET-756", "title": "订单查询接口偶发超时",
        "service": "order-service", "status": "resolved",
        "resolution": "数据库慢查询(order_items表按user_id查询缺索引)导致连接被长时间占用,"
                       "进而引发连接池排队。修复:补充复合索引,查询P99从1.2s降到40ms。",
        "resolved_at": "2026-03-15",
    },
    {
        "id": "TICKET-1203", "title": "payment-service对接的第三方支付网关抖动",
        "service": "payment-service", "status": "monitoring",
        "resolution": "第三方网关自身偶发抖动,已反馈对方技术团队跟进;我方已增加熔断和降级"
                       "(网关不可用时提示用户稍后重试而非无限等待),暂未彻底解决,持续观察中。",
        "resolved_at": None,
    },
]


def search_tickets(query: str = "", service: str = "") -> list[dict]:
    q = query.strip().lower()
    s = service.strip().lower()
    results = []
    for t in _TICKETS:
        service_match = (not s) or (s in t["service"].lower()) or (t["service"].lower() in s)
        if not service_match:
            continue
        if q and q not in t["title"].lower() and q not in t["resolution"].lower():
            continue
        results.append(t)
    return results
