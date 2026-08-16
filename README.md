# 企业智能运维诊断 Agent（Enterprise Intelligent AIOps Diagnosis Agent）

面试导向的 RAG + Agent 项目。完整架构设计见 [`docs/architecture.md`](docs/architecture.md)，
开发进度和故障排查手册见 [`docs/project_management.md`](docs/project_management.md)。

## 当前状态（自动生成骨架 + 真实联调后的状态，未夸大）

- RAG Pipeline（Chunking → BM25 + Dense → RRF Fusion → Reranker → Evidence）：已实现，**已用真实数据跑通**，见 [`docs/experiment_results.md`](docs/experiment_results.md)
- Agent Loop（Intent → Planner → Tool Loop(结构化Stop Condition) → Answer → Validator）：已实现，**已用真实query跑通**，包括一次真实的Abstention缺陷发现+修复（见experiment_results.md）
- 3个 Tool：knowledge_search（真实Pipeline）、log_query / service_metrics（mock数据，接口可替换真实系统）
- 9篇原创mock企业文档、30条结构化评测集（10关键词/10语义/5多证据/5知识库外）
- 单元测试：24个，全部通过（Chunking、RRF Fusion、Agent Stop Condition、Eval Metrics、Mock Planner收敛性）
- **Postgres+pgvector 生产路径代码已实现但本机环境暂未跑通**：宿主机 Docker Desktop 因未开启
  Windows "Virtual Machine Platform" 功能无法启动 WSL2，这需要管理员权限+重启修复。已改用
  `InMemoryDenseRetriever`（依赖注入，替换Dense检索的唯一实现）跑通全部实验，详见 `docs/experiment_results.md`
- **默认 Provider 是 Mock/占位实现**（见下方"重要限制"），当前所有数字反映占位Embedder/Reranker/LLM的真实能力，不代表生产级效果

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

### 方式A：离线跑通全部Pipeline+实验（不需要Docker/Postgres，本次就是这样验证的）

```bash
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scripts/offline_demo.py   # Retrieval评测+3组实验+Agent Demo，真实输出见 docs/experiment_results.md
.venv\Scripts\python -m pytest tests/unit -v   # 24个单元测试
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

## 目录结构

见 `docs/architecture.md` 第6节。

## 待办（下一步，未完成）

- [ ] 开启宿主机 Windows "Virtual Machine Platform" 功能（需管理员权限+重启），之后跑 `docker compose up -d postgres` + `scripts/ingest.py` + `eval/run_eval.py`，验证 Postgres+pgvector 生产路径和内存版路径数字一致
- [x] Chunk Size (256/512/1024) 对比实验 —— 已跑，真实数据见 `docs/experiment_results.md`
- [x] Dense-only / BM25-only / Hybrid 对比实验 —— 已跑，真实数据见 `docs/experiment_results.md`（结果和"Hybrid应该更好"的直觉不一致，已如实记录分析）
- [x] Abstention（拒答）机制验证 —— 联调中发现真实缺陷并修复，见 `docs/experiment_results.md`
- [ ] 换真实 Embedding 模型（`EMBEDDER_PROVIDER=openai`）重跑全部实验 —— 当前所有数字建立在占位Embedder之上，是下一步最重要的验证
- [ ] Reranker有无对比、Max Iterations对Task Success Rate影响 —— 还没跑
- [ ] FastAPI 集成测试（当前只有不依赖DB的单元测试）
- [ ] Ticket工单Tool（第4个Tool，MVP稳定后再加）
