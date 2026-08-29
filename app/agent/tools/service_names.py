"""Canonical service naming shared by read-only operational tools.

The LLM may produce human-facing Chinese service names while monitoring backends
use stable machine identifiers. Normalize only a small, explicit allowlist so a
fuzzy guess can never silently route a request to the wrong production service.
"""

SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "order-service": ("order-service", "order_service", "订单服务"),
    "payment-service": ("payment-service", "payment_service", "支付服务"),
    "inventory-service": ("inventory-service", "inventory_service", "库存服务"),
    "user-service": ("user-service", "user_service", "用户服务"),
}

KNOWN_SERVICES = frozenset(SERVICE_ALIASES)


def canonical_service_name(value: str) -> str:
    normalized = value.strip().lower()
    for canonical, aliases in SERVICE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return normalized


class TenantScopedService:
    """Resolve service aliases and fail closed before an adapter reads tenant data."""

    def __init__(self, allowed_services: set[str] | None = None):
        self.allowed_services = (
            None
            if allowed_services is None
            else frozenset(
                canonical_service_name(name) if name != "__self__" else name
                for name in allowed_services
            )
        )

    def scoped_service_name(self, value: str, *, self_query: bool = False) -> str:
        canonical = "__self__" if self_query else canonical_service_name(value)
        if self.allowed_services is not None and canonical not in self.allowed_services:
            raise PermissionError(f"当前租户无权访问服务 '{value}'")
        return canonical
