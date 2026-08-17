# 企业智能运维诊断 Agent V1 架构设计

版本：v1.0
定位：面试导向的技术深度项目（非生产级平台）
核心原则：规模可控，但每个模块都能被面试官一路问到原理、实现、指标、故障、优化、权衡。

---

## 0. 两处需要显式解决的设计张力

1. **30 条评测集 vs 五类评估体系的粒度**：10 条关键词检索 + 10 条语义检索 + 5 条多证据 + 5 条"知识库不存在"，要同时支撑 Retrieval/Reranker/Agent/Answer/System 五套指标。5 条样本算出的 Abstention Rate，错一条就是 20 个百分点的波动——**这是方向性验证，不是统计显著的结论**，必须在 Evaluation 报告里明确标注这一点，不能护短。
2. **Agent 自主决策 vs Stop Condition 的可测试性**：纯自由文本的 LLM 决策不可复现，无法写稳定回归测试。解决方式：**Planner 的输出必须是结构化 JSON（tool_name + reasoning + sufficient: bool），"选哪个 Tool"允许 LLM 自由发挥，"是否停止"必须基于结构化字段做确定性判断**，不允许从自由文本里"猜"是否该停。

---

## 1. 项目定位

面向企业内部技术人员的运维故障诊断 Agent。核心价值不是"检索文档"，而是把"用户报告一个异常现象"到"给出有证据支撑的诊断 + 排查建议"这个过程自动化，且全程可追溯、可验证、可拒答。

## 2. 用户场景

用户：SRE / 后端工程师 / 值班人员。
输入形态：故障描述、HTTP 状态码、日志片段、告警文本、模糊提问。

两类任务，Intent 阶段必须先区分：
- **纯知识问答**（"ECONNRESET 是什么意思"）→ 只需要 Knowledge Retrieval Tool
- **需要实时证据的诊断任务**（"订单服务 502 很多，帮我分析"）→ 需要 Log/Metrics Tool 配合

## 3. MVP 边界

**必须有**
- Agent Runtime：Intent → Planner → Tool Loop（结构化停止条件）→ Answer → Evidence Validation
- Knowledge Retrieval Tool：内部完整 BM25 + Dense + Hybrid Fusion + Reranker pipeline
- Log Query Tool（mock 数据，但接口设计为可替换为真实日志系统）
- Service Metrics Tool（mock 数据，同上）
- **Ticket 工单 Tool**（mock 数据，同上）——原计划"MVP稳定后再加"，前3个工具跑通+真实LLM联调
  验证过状态机稳定之后，已经加入，见下方"MVP 完成后的追加项"
- Evidence-based Answer + Abstention（无证据时拒答，不编造；Evidence Relevance 判断防止
  "分数过线但主题不相关"的证据被误判为有效证据，见 ADR-007）
- 30 条结构化评测集，跑出真实 Recall/Precision/MRR（不伪造数字）
- Retrieval Debug 数据结构全链路落库（这是"可扒性"的核心）
- 结构化日志，request_id 贯穿全链路
- Docker Compose 一键起（Postgres + pgvector + 服务，代码就绪，本机因宿主机虚拟化设置未验证）

**非 MVP（明确排除，作为"规模扩大后的演进方案"讨论）**
- Query Rewrite 的独立 LLM 调用（先规则兜底，评测发现"模糊问题召回差"再加）
- Redis / Milvus / Kafka / K8s / Neo4j / GraphRAG / Multi-Agent / 长期 Memory / LangGraph（见第 23-24 节）

## 3.1 MVP 完成后的追加项（真实开发过程中做的，非原计划）

- **DeepSeek 真实 LLM 接入**：替换 Mock 规则引擎，见 ADR-006
- **Ticket 工单 Tool**：4个工具协同（knowledge_search/log_query/service_metrics/ticket_search）
- **Evidence Relevance 判断**：ADR-007，修复真实联调发现的 Validator 判断粗糙问题
- **FastAPI 集成测试**：不依赖真实 Postgres，用 dependency_overrides + FakeSession 验证
  HTTP 契约和持久化代码路径
- 完整实验记录见 `docs/experiment_results.md`——包括几个和直觉不一致、如实记录而非回避的结果

## 4. 非 MVP 功能清单

| 功能 | 排除原因 | 引入信号 |
|---|---|---|
| Ticket 工单 Tool | 先把 3 个工具的协同跑扎实，再加第 4 个 | 前 3 个工具的 Tool Selection Accuracy 稳定 > 85% 后 |
| Query Rewrite | 增加一次 LLM 调用的延迟和成本，先看基线是否真的需要 | 评测集里"模糊/口语化"子集 Recall 明显低于其他子集 |
| Redis 缓存 | 没有实测出的缓存收益场景 | 实测发现同一 query/embedding 被高频重复请求 |
| Milvus | 数据量（几千~几万 chunk）远低于其性能拐点 | pgvector 实测 P95 查询延迟超过阈值，或向量规模破百万 |
| LangGraph | 手写 Loop 完全够用，且能讲清楚内部机制 | 状态管理/分支复杂到手写状态机难以维护 |
| Multi-Agent | 单 Agent + 多 Tool 已覆盖场景，拆分只增加协调开销 | 不同子任务需要完全独立的上下文/权限/模型 |
| 长期 Memory | 诊断任务通常单次会话内完成 | 产品定位变成"跨会话追踪某服务问题演变" |

---

## 5. 完整系统架构图

```
                                    ┌─────────────┐
                                    │    User      │
                                    └──────┬───────┘
                                           │ HTTP (FastAPI)
                                    ┌──────▼───────┐
                                    │  API Layer    │  request_id 生成
                                    └──────┬───────┘
                                           │
                                ┌──────────▼──────────┐
                                │   Agent Runtime       │
                                │  Intent → Planner      │
                                │  → Tool Loop → Answer  │
                                │  (结构化 Stop Condition)│
                                └──────────┬──────────┘
                                           │ Tool Calling (统一接口)
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
    ┌─────────▼──────────┐      ┌─────────▼─────────┐        ┌─────────▼─────────┐
    │ Knowledge Retrieval  │      │   Log Query Tool    │        │ Service Metrics    │
    │ Tool                 │      │   (mock, 可替换)     │        │ Tool (mock, 可替换) │
    │  ┌─────────────────┐│      └────────────────────┘        └───────────────────┘
    │  │ Query Processing ││
    │  └────────┬────────┘│
    │  ┌─────────▼────────┐│
    │  │ BM25 + Dense      ││ ← pgvector (Dense) + Postgres tsvector (BM25)
    │  │ Hybrid Fusion(RRF)││
    │  └────────┬────────┘│
    │  ┌─────────▼────────┐│
    │  │    Reranker        ││ ← Cross-Encoder / 可插拔
    │  └────────┬────────┘│
    │  ┌─────────▼────────┐│
    │  │  Evidence + Debug ││ → 全部中间结果落 retrieval_logs 表
    │  └──────────────────┘│
    └──────────────────────┘
              │
    (以上三个 Tool 的 Observation 汇总回 Agent State)
              │
    ┌─────────▼──────────┐
    │  Answer Generation   │  ← LLM Client（可插拔：Mock/OpenAI/Anthropic）
    └─────────┬──────────┘
    ┌─────────▼──────────┐
    │  Answer Validator     │  ← Evidence Grounding 校验，无证据则 Abstain
    └─────────┬──────────┘
    ┌─────────▼──────────┐
    │      Response          │  诊断 + 排查步骤 + 引用 + 置信度
    └──────────────────────┘

  旁路（贯穿全链路）：
  PostgreSQL（元数据/对话/日志/评测）  ←→ 所有模块
  Structured Logging + request_id       → 每个模块埋点
```

## 6. Agent Layer

职责：意图理解、任务规划、Tool 选择与调用、状态维护、循环控制、最终回答生成。**不直接实现检索逻辑**，只通过统一 Tool 接口调用 Knowledge Retrieval Tool。

## 7. Retrieval Layer（在 Knowledge Retrieval Tool 内部）

职责：Query 处理、BM25/Dense 双路召回、融合、精排、构造带引用的 Evidence，并输出完整调试信息。对 Agent Layer 暴露的是一个函数调用，但内部是完整独立的 Pipeline，可以脱离 Agent 单独跑评测（这是"RAG 和 Agent 分别能讲清楚"的架构落点）。

## 8. Tool Layer

统一抽象：所有 Tool 实现同一个接口（`name`, `description`, `input_schema`, `call(input) -> ToolResult`），Agent Runtime 不关心 Tool 内部实现细节，只关心输入输出契约和失败模式（timeout/error/empty）。

## 9. Data Layer

PostgreSQL 单一数据库承载：结构化元数据 + 向量（pgvector）+ 全文索引（tsvector）+ 对话记录 + 调试日志 + 评测结果。见第 14 节详细设计。

## 10. Evaluation Layer

独立于线上服务的评测子系统，直接调用 Retrieval/Agent 的内部接口（不经过 HTTP），批量跑评测集，产出五类指标。评测集与生产数据物理隔离（不同表/不同来源），避免"自证循环"。

## 11. Observability Layer

结构化日志 + request_id 贯穿 + 全链路耗时埋点（Retrieval/Reranker/Tool/LLM 各自独立计时），落库到 `agent_runs` 和 `retrieval_logs`，支持"用户说系统很慢，逐层查是哪一层慢"这个诊断场景。

## 12. 数据流（RAG 部分）

```
原始文档(Markdown) → 清洗 → Document(写入documents表,记录version)
  → Chunking(按策略) → Chunk(写入document_chunks,含metadata)
  → Embedding(batch) → 写入embedding列(pgvector)
———— 检索时 ————
Query → [规则兜底的Query Processing，MVP暂不做LLM Rewrite]
  → 并行: BM25(tsvector) / Dense(cosine, pgvector)
  → RRF融合 → 候选池(~30) → Reranker(Cross-Encoder) → Top5
  → Context Builder(拼接+截断+引用标记) → Evidence
```

## 13. 一次完整请求的时序图

```
User          API          Agent          KB-Tool        Retrieval-Pipeline    LLM         DB
 │             │             │               │                  │              │           │
 │──query────▶│             │               │                  │              │           │
 │             │──run_id────▶│               │                  │              │           │
 │             │             │──Intent LLM──────────────────────────────────▶│           │
 │             │             │◀─────intent:诊断任务────────────────────────────│           │
 │             │             │──Planner LLM(结构化JSON)───────────────────────▶│           │
 │             │             │◀──{tool:kb_search, sufficient:false}───────────│           │
 │             │             │──call(kb_search)─▶│                  │              │           │
 │             │             │               │──query───────────▶│              │           │
 │             │             │               │              (BM25+Dense+Fusion+Rerank)         │
 │             │             │               │◀───evidence+debug──│              │           │
 │             │             │               │──────────────────────────────────────────▶写retrieval_logs
 │             │             │◀───Observation────│                  │              │           │
 │             │             │──Planner LLM(第2轮)────────────────────────────▶│           │
 │             │             │◀─{tool:service_metrics, sufficient:false}────────│           │
 │             │             │──call(service_metrics)─────────────────────▶(mock)          │
 │             │             │◀───Observation(error_rate上升)───────────────────│           │
 │             │             │──Planner LLM(第3轮)────────────────────────────▶│           │
 │             │             │◀─{sufficient:true}──────────────────────────────│           │
 │             │             │──Answer LLM(evidence汇总)──────────────────────▶│           │
 │             │             │◀───draft answer + citations────────────────────│           │
 │             │             │──Validator(证据校验)                                          │
 │             │             │──────────────────────────────────────────────────────────▶写agent_runs
 │◀──response──│◀────────────│               │                  │              │           │
```

关键点：每一轮 Planner 调用都是一次独立的、结构化输出的 LLM 请求，不是一次性把所有 Tool 结果丢给 LLM 自由发挥。

---

## 14. PostgreSQL 数据库设计

```sql
knowledge_sources(id UUID PK, name TEXT, source_type TEXT, created_at TIMESTAMPTZ)

documents(
  id UUID PK, source_id UUID FK, title TEXT, raw_content TEXT,
  metadata JSONB,           -- {service, doc_type}
  version INT,              -- embedding模型升级时用于追踪
  created_at TIMESTAMPTZ
)
-- index: source_id(btree), metadata(GIN)

document_chunks(
  id UUID PK, document_id UUID FK, chunk_index INT, content TEXT,
  embedding VECTOR(384),    -- 维度依所选embedder而定
  metadata JSONB, embedding_version INT,
  created_at TIMESTAMPTZ
)
-- index: embedding(HNSW), document_id(btree), to_tsvector('simple',content)(GIN, BM25用)

conversations(id UUID PK, user_id TEXT, created_at TIMESTAMPTZ)
messages(id UUID PK, conversation_id UUID FK, role TEXT, content TEXT, created_at TIMESTAMPTZ)
-- index: (conversation_id, created_at)

agent_runs(
  id UUID PK, conversation_id UUID FK, request_id TEXT UNIQUE,
  final_answer TEXT, confidence FLOAT, status TEXT,  -- success/abstained/error
  total_latency_ms INT, token_usage JSONB, created_at TIMESTAMPTZ
)

tool_calls(
  id UUID PK, agent_run_id UUID FK, iteration INT, tool_name TEXT,
  input JSONB, output JSONB, latency_ms INT, status TEXT, created_at TIMESTAMPTZ
)

retrieval_logs(
  id UUID PK, agent_run_id UUID FK, tool_call_id UUID FK,
  query TEXT, rewritten_query TEXT,
  bm25_candidates JSONB, dense_candidates JSONB, fusion_candidates JSONB,
  rerank_candidates JSONB, final_context UUID[],
  scores JSONB, latency_breakdown JSONB, created_at TIMESTAMPTZ
)

evaluation_cases(
  id UUID PK, question TEXT, ground_truth_chunk_ids UUID[], expected_answer TEXT,
  category TEXT,     -- keyword/semantic/multi_evidence/not_in_kb
  difficulty TEXT, created_at TIMESTAMPTZ
)

evaluation_results(
  id UUID PK, case_id UUID FK, eval_run_id TEXT,
  recall_at_k FLOAT, precision_at_k FLOAT, mrr FLOAT,
  tool_selection_correct BOOLEAN, task_success BOOLEAN,
  answer TEXT, created_at TIMESTAMPTZ
)
```

设计要点：主键 UUID；外键必查字段 btree；embedding 向量索引 HNSW；全文检索 GIN；`retrieval_logs`/`evaluation_results` 不缓存（审计数据，写多读少）；`embedding_version` 字段专门应对 Embedding 模型升级时的兼容性排查。

---

## 15. Knowledge Retrieval Tool 接口

```python
@dataclass
class RetrievalDebugInfo:
    query: str
    rewritten_query: str | None
    bm25_candidates: list[ScoredChunk]      # 分数 + chunk_id
    dense_candidates: list[ScoredChunk]
    fusion_candidates: list[ScoredChunk]
    rerank_candidates: list[ScoredChunk]
    final_context: list[Chunk]
    latency_breakdown: dict[str, float]     # {"bm25_ms":..,"dense_ms":..,"rerank_ms":..}

@dataclass
class ToolResult:
    success: bool
    evidence: list[Evidence]     # 给LLM用的精简版(不含debug)
    debug: RetrievalDebugInfo | None   # 只落库，不进LLM context
    error: str | None

class KnowledgeRetrievalTool(Tool):
    name = "knowledge_search"
    description = "检索企业技术文档、故障案例、运维SOP"
    input_schema = {"query": str, "top_k": int, "filters": dict | None}

    def call(self, query: str, top_k: int = 5, filters: dict | None = None) -> ToolResult: ...
```

`debug` 字段是解决"Tool 输出既要给 LLM 用又要支撑排查"这个接口张力的关键：evidence 精简后进 LLM context 控制 token 成本，debug 全量落 `retrieval_logs` 表供事后排查，两者物理分离。

## 16. Log Query Tool 接口

```python
class LogQueryTool(Tool):
    name = "log_query"
    description = "查询指定服务在时间范围内的日志"
    input_schema = {"service": str, "time_range": str, "level": str | None}

    def call(self, service: str, time_range: str, level: str = "ERROR") -> ToolResult:
        # MVP: 从 data/mock/logs.py 的预置场景中按 service 匹配返回
        # 生产替换点: 接入真实日志系统(如ELK) API
        ...
```

## 17. Service Metrics Tool 接口

```python
class ServiceMetricsTool(Tool):
    name = "service_metrics"
    description = "查询指定服务的实时指标：CPU/Memory/QPS/ErrorRate/P95延迟/状态"
    input_schema = {"service": str}

    def call(self, service: str) -> ToolResult:
        # MVP: mock数据，预置几个服务的"正常"和"异常"两套快照
        ...
```

## 17.1 Ticket Search Tool 接口（MVP稳定后追加的第4个工具）

```python
class TicketSearchTool(Tool):
    name = "ticket_search"
    description = "查询历史故障工单及其解决方案，可按服务名和/或关键词检索"
    input_schema = {"service": str, "query": str}  # 均可选

    def call(self, service: str = "", query: str = "") -> ToolResult:
        # MVP: mock数据(data/mock/tickets.py)，简单字符串匹配；
        # 生产替换点：接入Jira/内部工单系统API，函数签名不变
        ...
```

和 knowledge_search 的区别：knowledge_search 检索的是文档/SOP这类"通用知识"，
ticket_search 检索的是"这个具体问题历史上出现过、怎么修的"这种结构化的
问题-方案记录，信息密度更高但覆盖面更窄（只覆盖发生过的故障，不覆盖纯知识性问题）。
两者在 Agent Loop 里是互补关系，不是互相替代——这也是为什么 Validator 把
ticket_search 的非空结果计入 grounding 证据（和 log_query/service_metrics 同类），
而不是像 knowledge_search 那样需要额外过 Evidence Relevance 判断：因为
ticket_search 走的是精确字段匹配（service名/关键词），不是语义检索，
出现"分数过线但主题不相关"这类问题的概率本身就低很多。

## 18. Agent State 设计

```python
@dataclass
class PlannerDecision:
    reasoning: str            # LLM的自然语言解释(仅用于日志展示)
    tool_name: str | None     # None表示不需要再调用工具
    tool_input: dict | None
    sufficient: bool          # 结构化字段，Stop Condition只认这个，不解析自然语言

@dataclass
class AgentState:
    request_id: str
    query: str
    intent: str                          # knowledge_qa / diagnosis
    iteration: int = 0
    max_iterations: int = 5
    tool_budget: dict[str, int] = field(default_factory=dict)  # 每个tool最多调用次数
    observations: list[ToolResult] = field(default_factory=list)
    start_time: float
    timeout_s: float = 30.0
    status: str = "running"              # running/answered/abstained/timeout/error

    def should_stop(self, decision: PlannerDecision) -> tuple[bool, str]:
        if decision.sufficient:
            return True, "planner_sufficient"
        if self.iteration >= self.max_iterations:
            return True, "max_iterations"
        if time.time() - self.start_time > self.timeout_s:
            return True, "timeout"
        if decision.tool_name and self.tool_budget.get(decision.tool_name, 0) <= 0:
            return True, "tool_budget_exhausted"
        return False, ""
```

Stop Condition 是纯函数、可单测——这是解决第 0 节"张力 2"的具体落地。

## 19. Retrieval Debug 数据结构

见第 15 节 `RetrievalDebugInfo`。设计原则：**每一层的输入输出都要能独立还原**，排查"为什么没召回正确文档"时，可以逐层对比 `bm25_candidates` / `dense_candidates` / `fusion_candidates` / `rerank_candidates` 里 ground_truth chunk 的排名变化，精确定位是哪一层把它丢了。

## 20. Evaluation Dataset 设计

```json
{
  "id": "eval_001",
  "question": "订单服务返回502 Bad Gateway，可能是什么原因",
  "category": "keyword",
  "ground_truth_chunk_ids": ["<uuid>", "<uuid>"],
  "expected_answer_contains": ["upstream", "超时", "nginx"],
  "difficulty": "easy",
  "requires_tool": ["knowledge_search"]
}
```

30 条构成：10 关键词检索 / 10 语义检索 / 5 多证据（需要融合多个 chunk）/ 5 知识库不存在（测试 Abstention）。**问题和 ground_truth 由我们自己构造 mock 数据，构造评测集时不看 Retriever 实现代码，避免"顺手把答案设计成 Retriever 容易召回的样子"这种隐性自证循环**。

---

## 21-22. 技术选型、替代方案与 Trade-off（ADR 摘要）

| 决策 | 理由 | 替代方案 | Trade-off | 何时改变 |
|---|---|---|---|---|
| PostgreSQL+pgvector | 单数据库管理结构化+向量数据，MVP规模不需要专用向量库 | Milvus | Milvus大规模场景更专业，但增加基础设施复杂度 | 向量规模破百万或P95延迟超阈值 |
| BM25(tsvector)+Dense混合 | 关键词类(错误码/服务名)和语义类查询各有优势 | 纯Dense | 纯Dense在精确匹配上召回差，已用实验验证(见eval) | 若实测BM25贡献持续<5%可简化 |
| 手写Agent Loop | 逻辑简单，需要完全理解内部机制 | LangGraph | 手写在复杂分支下难维护 | 状态管理复杂到手写状态机失控 |
| 可插拔LLM/Embedder | 无外部API依赖也能跑通、可测试、成本可控 | 直接硬编码OpenAI | 默认mock质量有限，需要真实key才有真实语义效果 | 用户提供API Key后切换 |
| 不用Redis | 无实测缓存收益场景 | 加缓存层 | 无 | 实测出高频重复query |

完整 ADR 见 `docs/adr/` （后续按需补充独立文件）。

## 23-24. 明确不用的技术及引入门槛

见第 4 节表格，此处不重复。

---

## 25. 10 个最重要的实验

1. Chunk Size: 256/512/1024 对比 Recall@5
2. Chunk Overlap: 0/50/100 对比跨chunk问题表现
3. Dense-only / BM25-only / Hybrid 对比（核心实验）
4. Reranker 有无对比 Precision@5
5. Retriever候选数量(10/30/50)对Recall上限和延迟的影响
6. RRF融合权重比例对比
7. Max Iterations(3/5/8)对Task Success Rate和成本的影响
8. Embedder选择对比(占位hash embedder vs 真实模型，若配置了key)
9. Tool Budget限制对无限循环防护效果的验证
10. Answer Validator开关对Abstention正确率的影响

## 26. 20 个最可能出现的故障

同第一轮 Step 12 列表（Recall骤降/Reranker误杀/Chunk边界切断/Embedding版本不兼容/索引未刷新/Metadata过滤/BM25分词/融合权重不合理/幻觉/无限循环/Tool超时/LLM 429/Prompt截断/Prompt Injection/连接池耗尽/N+1查询/评测不可复现/多轮上下文污染/敏感信息泄露/冷启动空索引），完整版见 `docs/project_management.md` 故障排查手册章节。

## 27-30. 四棵排查树

见 `docs/project_management.md` 独立章节（含症状/原因/观测/验证/修复/预防/回归测试 完整表格）。

## 31. 50 个高频追问问题

见第一轮回答，完整复用，已收录进 `docs/project_management.md`。

## 32. 开发 Roadmap

见 `docs/project_management.md`。

---

## 附：默认 Provider 说明（重要，避免误解评测数字）

MVP 默认使用**可插拔但轻量级的占位实现**，不依赖外部网络/API Key 也能端到端跑通：
- Embedder 默认：确定性 hashing embedding（TF-IDF风格特征 + 随机投影降维），语义表达能力弱于真实模型，仅用于验证 Pipeline 正确性。
- LLM Client 默认：Mock 规则引擎，用于验证 Agent Loop 状态机、Stop Condition、Tool 调用契约的正确性，**不具备真实语义推理能力**。
- 两者均通过环境变量切换为真实 Provider（`EMBEDDER_PROVIDER=openai`, `LLM_PROVIDER=anthropic` 等），接口不变。

**这意味着：在未配置真实 API Key 前跑出的 Recall/Precision 数字，反映的是"占位 Embedder 的真实能力"，不是"生产级 Embedding 模型的预期效果"——两者不能混淆，评测报告会明确标注所用 Provider。**
