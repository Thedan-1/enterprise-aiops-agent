from app.auth.service import AuthContext


ROLE_TOOLS = {
    "viewer": {"knowledge_search"},
    "operator": {"knowledge_search", "service_metrics", "log_query", "ticket_search"},
    "auditor": set(),
}


def allowed_tools(context: AuthContext) -> set[str]:
    return set(ROLE_TOOLS.get(context.role, set()))


def can_read_audit(context: AuthContext) -> bool:
    return context.role == "auditor"

