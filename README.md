# 企业智能运维诊断 Agent（Enterprise Intelligent AIOps Diagnosis Agent）

面试导向的 RAG + Agent 项目。完整架构设计见 [`docs/architecture.md`](docs/architecture.md)，
开发进度和故障排查手册见 [`docs/project_management.md`](docs/project_management.md)。

## 当前状态（自动生成骨架后的真实状态，未夸大）

- RAG Pipeline（Chunking → BM25 + Dense → RRF Fusion → Reranker → Evidence）：已实现，可独立于 Agent 运行评测
- Agent Loop（Intent → Planner → Tool Loop(结构化Stop Condition) → Answer → Validator）：已实现
- 3个 Tool：knowledge_search（真实Pipeline）、log_query / service_metrics（mock数据，接口可替换真实系统）
- 9篇原创mock企业文档、30条结构化评测集（10关键词/10语义/5多证据/5知识库外）
- 单元测试覆盖：Chunking、RRF Fusion、Agent Stop Condition、Eval Metrics、Mock Planner收敛性
- **默认 Provider 是 Mock/占位实现**（见下方"重要限制"），未配置真实 API Key 前，跑出来的
  Recall/Precision数字反映的是占位Embedder的真实能力，不代表生产级效果

## 重要限制：默认 Provider 是 Mock/占位实现

| 组件 | 默认实现 | 说明 |
|---|---|---|
| Embedder | `mock_hash`：字符n-gram hashing | 无需下载模型/联网，能跑通Pipeline，语义能力弱于真实Embedding模型 |
| Reranker | `heuristic`：词面重合度 | 无需下载模型，能验证精排流程，效果弱于Cross-Encoder |
| LLM | `mock`：规则引擎 | 能驱动Agent Loop的状态机/工具调用/停止条件，不具备真实推理能力 |

切换为真实Provider：编辑 `.env`，设置 `EMBEDDER_PROVIDER=openai` + `OPENAI_API_KEY`，
`RERANKER_PROVIDER=cross_encoder`（需要 `pip install sentence-transformers`），
`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`。接口不变，代码不用改。

## 快速开始

```bash
cp .env.example .env
pip install -r requirements.txt
docker compose up -d postgres
python scripts/ingest.py               # 灌入9篇mock文档
python eval/run_eval.py --with-agent   # 跑Retrieval评测 + Agent评测
pytest tests/unit -v                   # 单元测试(不需要数据库)
uvicorn app.main:app --reload          # 启动API, POST /api/chat {"query": "..."}
```

## 目录结构

见 `docs/architecture.md` 第6节。

## 待办（下一步，未完成）

- [ ] 实际启动 Postgres+pgvector 并跑通 ingest + eval 全链路，把真实数字写回 architecture.md 的实验章节
- [ ] Chunk Size (256/512/1024) 对比实验的真实数据
- [ ] Dense-only / BM25-only / Hybrid 对比实验的真实数据
- [ ] FastAPI 集成测试（当前只有不依赖DB的单元测试）
- [ ] Ticket工单Tool（第4个Tool，MVP稳定后再加）
