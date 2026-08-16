"""模拟日志查询。生产环境替换点：接入ELK/Loki等日志系统API，函数签名不变。"""

_LOG_SCENARIOS = {
    "order-service": [
        "2026-08-17T10:12:03Z ERROR order-service: upstream timeout connecting to payment-service (504)",
        "2026-08-17T10:12:05Z ERROR order-service: nginx upstream prematurely closed connection while reading response header from upstream, client: 10.0.2.11, upstream: order-service:8080",
        "2026-08-17T10:12:11Z ERROR order-service: connection pool exhausted, waited 5000ms for available connection",
        "2026-08-17T10:12:20Z WARN  order-service: request queue depth exceeded threshold (500)",
    ],
    "inventory-service": [
        "2026-08-17T09:55:01Z WARN  inventory-service: memory usage above 85% threshold",
        "2026-08-17T09:55:40Z ERROR inventory-service: GC pause exceeded 800ms, possible memory pressure",
    ],
}

_DEFAULT_LOGS = ["2026-08-17T10:00:00Z INFO  {service}: no error-level logs in the requested time range"]


def get_logs(service: str, time_range: str = "last_10_minutes", level: str = "ERROR") -> list[str]:
    key = service.strip().lower()
    for name, logs in _LOG_SCENARIOS.items():
        if name in key or key in name:
            filtered = [l for l in logs if level.upper() in l] if level else logs
            return filtered or [f"2026-08-17T10:00:00Z INFO  {name}: no {level}-level logs in {time_range}"]
    return [line.format(service=service) for line in _DEFAULT_LOGS]
