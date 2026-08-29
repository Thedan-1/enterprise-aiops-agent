from app.agent.tools.ticket_search import TicketSearchTool
from data.mock.tickets import search_tickets


def test_search_by_service_returns_matching_tickets():
    results = search_tickets(service="order-service")
    assert len(results) >= 1
    assert all("order-service" in t["service"] for t in results)


def test_search_by_unknown_service_returns_empty():
    assert search_tickets(service="nonexistent-service") == []


def test_search_by_query_keyword_filters_within_service_scope():
    results = search_tickets(query="502")
    assert any("502" in t["title"] for t in results)


def test_ticket_search_tool_success_with_results():
    tool = TicketSearchTool()
    result = tool.call(service="order-service")
    assert result.success is True
    assert "TICKET" in result.summary
    assert result.debug["tickets"]


def test_ticket_search_tool_success_with_no_results():
    tool = TicketSearchTool()
    result = tool.call(service="nonexistent-service")
    assert result.success is True
    assert result.debug["tickets"] == []


def test_ticket_tool_accepts_chinese_business_service_name():
    result = TicketSearchTool().call(service="订单服务")

    assert result.success is True
    assert result.debug["tickets"]
    assert all(ticket["service"] == "order-service" for ticket in result.debug["tickets"])
