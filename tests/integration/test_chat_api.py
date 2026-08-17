"""FastAPI /api/chat 集成测试。

不用 app.main:app（它的lifespan会连真实Postgres），而是单独拼一个只挂
chat router 的test app，用 dependency_overrides 换掉 get_agent_runtime 和
get_session。AgentRuntime本身是真的（真实Pipeline+真实MockLLMClient+真实
3个Tool），只有"连数据库持久化"这一步换成FakeSession——这样测的是
"HTTP请求进来 -> Agent真的跑一遍 -> 响应契约对不对 -> 持久化代码路径
有没有抛异常"，而不是简单mock掉整个Agent只测路由能不能通。
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.loop import AgentRuntime
from app.agent.tools.kb_search import KnowledgeSearchTool
from app.agent.tools.log_query import LogQueryTool
from app.agent.tools.service_metrics import ServiceMetricsTool
from app.agent.tools.ticket_search import TicketSearchTool
from app.api.chat import get_agent_runtime, router
from app.core.embedder import get_embedder
from app.core.llm_client import MockLLMClient
from app.db.session import get_session
from app.rag.reranker import get_reranker
from scripts.offline_demo import build_pipeline, load_and_chunk


class FakeSession:
    """SQLAlchemy Session的最小替身：只支持_persist_run实际用到的add/flush/commit，
    flush时模拟"数据库分配主键"的效果(真实DB是在flush/insert时才populate默认值)。"""

    def __init__(self):
        self.added: list = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self):
        self.flush()
        self.committed = True


@pytest.fixture(scope="module")
def client():
    chunks, doc_titles = load_and_chunk(chunk_size=512, overlap=50)
    pipeline = build_pipeline(chunks, get_embedder(), get_reranker())
    tools = [KnowledgeSearchTool(pipeline, doc_titles), LogQueryTool(), ServiceMetricsTool(), TicketSearchTool()]
    runtime = AgentRuntime(MockLLMClient(), tools, max_iterations=5, timeout_s=30.0)

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    test_app.dependency_overrides[get_agent_runtime] = lambda: runtime

    fake_session = FakeSession()
    test_app.dependency_overrides[get_session] = lambda: fake_session

    with TestClient(test_app) as c:
        c.fake_session = fake_session  # 挂在client上方便测试里取出来断言持久化行为
        yield c


def test_chat_diagnosis_query_returns_expected_shape(client):
    resp = client.post("/api/chat", json={"query": "order-service最近大量出现502，帮我分析可能原因"})
    assert resp.status_code == 200
    body = resp.json()

    assert uuid.UUID(body["request_id"])  # 是合法UUID
    assert body["status"] in ("answered", "abstained")
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["iterations"] >= 1
    assert isinstance(body["answer"], str) and len(body["answer"]) > 0


def test_chat_not_in_kb_query_abstains(client):
    resp = client.post("/api/chat", json={"query": "公司的年假申请流程是什么"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "abstained"
    assert body["confidence"] < 0.5


def test_chat_missing_query_field_returns_422(client):
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 422


def test_chat_persists_agent_run_and_tool_calls(client):
    client.fake_session.added.clear()
    resp = client.post("/api/chat", json={"query": "什么是缓存穿透"})
    assert resp.status_code == 200

    from app.db.models import AgentRun, ToolCall

    added_types = [type(o) for o in client.fake_session.added]
    assert AgentRun in added_types
    assert ToolCall in added_types
    assert client.fake_session.committed is True
