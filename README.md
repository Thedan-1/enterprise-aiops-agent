# 企业智能运维诊断 Agent（Enterprise Intelligent AIOps Diagnosis Agent）

面试导向的 RAG + Agent 项目。完整架构设计见 [`docs/architecture.md`](docs/architecture.md)，
开发进度和故障排查手册见 [`docs/project_management.md`](docs/project_management.md)，
真实实验数据见 [`docs/experiment_results.md`](docs/experiment_results.md)，
**面试讲稿大纲 + 100题问题库见 [`docs/interview_prep.md`](docs/interview_prep.md)**。

## 当前状态（真实联调后的状态，未夸大）

- **三个核心组件（Embedder / Reranker / LLM）现在全部是真实模型/真实API，不再有任何占位实现**——见下方"Provider 状态"
- RAG Pipeline（Chunking → BM25 + Dense → RRF Fusion → Reranker → Evidence）：已实现，**用占位实现和真实模型各跑了一整套对比实验**（Chunk Size / Dense-BM25-Hybrid / Reranker有无），见 [`docs/experiment_results.md`](docs/experiment_results.md)——换真实模型后发现了一个反直觉的重要结果：真实 Cross-Encoder Reranker 在当前小规模评测集上反而拉低了 Recall/Precision/MRR，如实记录分析，没有回避
- Agent Loop（Intent → Planner → Tool Loop(结构化Stop Condition) → Answer → Evidence Validation）：已实现，**真实DeepSeek LLM跑通**，联调中发现并修复了两个真实缺陷（Planner跳过知识库检索、Validator误判不相关证据为有效证据），见 ADR-006/ADR-007
- **4个 Tool**：knowledge_search（真实Pipeline）、log_query / service_metrics / ticket_search（mock数据，接口可替换真实系统）
- 9篇原创mock企业文档、30条结构化评测集（10关键词/10语义/5多证据/5知识库外）
- 单元测试 33 个 + 集成测试 4 个，全部通过；集成测试刻意用 Mock 组件（不依赖 `.env` 配置），保证测试套件快、确定性、不受环境影响
- **Postgres+pgvector 生产路径代码已实现但本机环境暂未跑通**：宿主机 Docker Desktop 因未开启
  Windows "Virtual Machine Platform" 功能无法启动 WSL2，这需要管理员权限+重启修复（用户自行处理中）。已改用
  `InMemoryDenseRetriever`（依赖注入，替换Dense检索的唯一实现）跑通全部实验，详见 `docs/experiment_results.md`

## Provider 状态（当前 `.env` 实际配置）

| 组件 | 当前配置 | 说明 |
|---|---|---|
| Embedder | `local_st`：**真实模型** `BAAI/bge-small-zh-v1.5`（本地加载，不需要API Key） | DeepSeek没有Embedding API（实测404，非猜测），改用本地开源中文模型 |
| Reranker | `cross_encoder`：**真实模型** `BAAI/bge-reranker-base`（本地加载，不需要API Key） | 见上方"反直觉结果"，已如实记录，不是"能跑就等于有效" |
| LLM | `deepseek`：**真实API**（`deepseek-chat`） | 真实推理，Agent Demo的回答质量和Mock规则引擎不是一个量级 |

`sentence-transformers`（Embedder/Reranker用）首次运行会从HuggingFace下载模型权重（各几百MB），
之后离线可用。仍保留 `mock_hash`/`heuristic`/`mock` 作为零依赖的默认占位实现（见 `.env.example`），
方便别人clone这个项目时不用等模型下载就能跑通Pipeline骨架。

## 快速开始

### 方式A：离线跑通全部Pipeline+实验（不需要Docker/Postgres，本次就是这样验证的）

```bash
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts/offline_demo.py   # Retrieval评测+5组实验+4工具Agent Demo，真实输出见 docs/experiment_results.md
.venv\Scripts\python -m pytest tests/ -v       # 33个单元测试 + 4个集成测试
```

### 方式B：完整生产路径（需要 Docker 能正常启动 Postgres+pgvector）

```bash
cp .env.example .env
pip install -r requirements.txt
docker compose up -d postgres
python scripts/ingest.py               # 灌入9篇mock文档到pgvector
python eval/run_eval.py --with-agent   # 跑Retrieval评测 + Agent评测（走DB）
uvicorn app.main:app --reload          # 启动API, POST /api/chat {"query": "..."}
```

### 方式C：浏览器里直接对话（不需要Docker/Postgres，有界面）

```bash
uvicorn app.offline_app:app --host 127.0.0.1 --port 8001
```

打开 `http://127.0.0.1:8001`。复用方式A的内存版Pipeline，不做数据库持久化（这是它和
`app/main.py`唯一的功能性差异，Agent行为完全一致）。界面左侧是架构Pipeline示意图和
系统状态，右侧对话区域能看到每次问答的置信度、状态（已回答/已拒答）、完整的工具调用
轨迹（含每条证据的rerank分数）。首次问答用的是真实DeepSeek，单次耗时15~40秒。

## 目录结构

见 `docs/architecture.md` 第6节。

## 待办（下一步，未完成）

- [ ] 开启宿主机 Windows "Virtual Machine Platform" 功能（需管理员权限+重启），之后跑 `docker compose up -d postgres` + `scripts/ingest.py` + `eval/run_eval.py`，验证 Postgres+pgvector 生产路径和内存版路径数字一致 —— 唯一还卡着的事，用户自行处理中
- [x] Chunk Size (256/512/1024) 对比实验 —— 占位/真实Embedder各跑一遍，结论会随Embedder变化，见 `docs/experiment_results.md`
- [x] Dense-only / BM25-only / Hybrid 对比实验 —— 占位/真实Embedder各跑一遍，真实Embedder下Hybrid才体现出优势
- [x] Reranker 有无对比实验 —— 占位/真实Reranker各跑一遍，**真实Cross-Encoder反而让指标下降**，如实记录未回避
- [x] Max Iterations (3/5/8) 对比实验 —— 已跑，真实发现是 tool_budget 而非 max_iterations 在起限制作用，换真实模型后收敛率明显提升
- [x] Abstention（拒答）机制验证 —— 联调中发现真实缺陷并修复
- [x] 接入真实LLM（DeepSeek）—— 已完成，发现并修复了Planner层的防幻觉gap（ADR-006）
- [x] 修复"证据主题不相关但压线通过分数阈值"导致status误判为answered的问题 —— 已修复（ADR-007），有回归测试
- [x] FastAPI 集成测试 —— 已完成，`tests/integration/test_chat_api.py`
- [x] Ticket工单Tool（第4个Tool）—— 已完成
- [x] 真实 Embedding 模型 + 真实 Cross-Encoder Reranker —— 已完成（本地开源模型，不需要OpenAI Key），重跑全部Retrieval实验，见ADR-008
- [ ] Reranker反直觉结果的根因排查 —— 需要更大规模知识库/评测集才能验证，当前样本量下无法下结论
- [ ] Agent Run 延迟优化 —— 真实模型下已降到20~31秒/次，仍主要是LLM串行调用开销，还没做并行化/流式
- [ ] 多轮对话能力 —— Conversation/Message表已设计，还没有实际跑过多轮场景的测试
