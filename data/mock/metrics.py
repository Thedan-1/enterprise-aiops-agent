"""模拟服务指标快照。生产环境替换点：接入Prometheus/云监控API，函数签名不变。"""

_SNAPSHOTS = {
    "order-service": {
        "status": "degraded",
        "cpu_percent": 78,
        "memory_percent": 65,
        "qps": 342,
        "error_rate": 0.18,
        "p95_latency_ms": 2400,
    },
    "payment-service": {
        "status": "healthy",
        "cpu_percent": 35,
        "memory_percent": 42,
        "qps": 210,
        "error_rate": 0.002,
        "p95_latency_ms": 180,
    },
    "user-service": {
        "status": "healthy",
        "cpu_percent": 28,
        "memory_percent": 38,
        "qps": 500,
        "error_rate": 0.001,
        "p95_latency_ms": 90,
    },
    "inventory-service": {
        "status": "degraded",
        "cpu_percent": 55,
        "memory_percent": 88,
        "qps": 120,
        "error_rate": 0.04,
        "p95_latency_ms": 950,
    },
}

_DEFAULT = {
    "status": "unknown",
    "cpu_percent": None,
    "memory_percent": None,
    "qps": None,
    "error_rate": None,
    "p95_latency_ms": None,
}


def get_metrics(service: str) -> dict:
    key = service.strip().lower()
    for name, snap in _SNAPSHOTS.items():
        if name in key or key in name:
            return {"service": name, **snap}
    return {"service": service, **_DEFAULT}
