"""验证'查自己'这条路径真的会走真实数据源(data/real/*)而不是mock表，
以及mock路径仍然完全不受影响——这两件事都要测，防止以后有人改代码时
不小心把self-query判断弄丢，或者反过来把真实数据源接到了mock查询上。"""
from app.agent.tools.log_query import LogQueryTool
from app.agent.tools.service_metrics import ServiceMetricsTool, _is_self_query
from data.real.host_metrics import get_host_metrics


def test_is_self_query_matches_expected_phrasings():
    for phrase in ["self", "本机", "这个系统", "AIOps-Agent", "aiops agent", "这台机器"]:
        assert _is_self_query(phrase), f"'{phrase}' 应该被识别为self-query"


def test_is_self_query_does_not_match_mock_services():
    for phrase in ["order-service", "payment-service", "inventory-service", "redis"]:
        assert not _is_self_query(phrase)


def test_get_host_metrics_returns_real_live_values():
    m = get_host_metrics()
    assert 0.0 <= m["cpu_percent"] <= 100.0
    assert 0.0 <= m["memory_percent"] <= 100.0
    assert m["process_count"] > 0
    assert m["status"] in ("healthy", "degraded")


def test_service_metrics_tool_routes_self_query_to_real_data():
    tool = ServiceMetricsTool()
    result = tool.call(service="本机")
    assert result.success is True
    assert "进程数" in result.summary
    assert "process_count" in result.debug


def test_service_metrics_tool_routes_normal_query_to_mock():
    tool = ServiceMetricsTool()
    result = tool.call(service="order-service")
    assert result.success is True
    assert "QPS" in result.summary  # mock数据结构里才有QPS字段,真实host数据没有


def test_service_metrics_tool_accepts_chinese_business_service_name():
    result = ServiceMetricsTool().call(service="订单服务")

    assert result.success is True
    assert "order-service" in result.summary
    assert result.debug["service"] == "order-service"


def test_log_query_tool_routes_self_query_to_real_log_file():
    tool = LogQueryTool()
    result = tool.call(service="这个系统")
    assert result.success is True
    assert "AIOps Agent" in result.summary


def test_log_query_tool_accepts_chinese_business_service_name():
    result = LogQueryTool().call(service="订单服务")

    assert result.success is True
    assert any("order-service" in line for line in result.debug["raw_lines"])


def test_log_query_distinguishes_unknown_service_from_no_error_logs():
    result = LogQueryTool().call(service="ghost-service")

    assert result.success is False
    assert result.error == "未识别服务 'ghost-service'，无法确认是否存在错误日志"
