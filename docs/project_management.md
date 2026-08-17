# 项目管理与故障排查手册

## 1. 开发 Roadmap

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 0 | 需求与架构（本文档 + architecture.md） | ✅ 完成 |
| Phase 1 | 数据层：mock企业文档、DB models、docker-compose | ✅ 完成（代码就绪，Postgres本机未验证，见下方说明） |
| Phase 2 | Chunking + Embedding + pgvector 灌入 | ✅ 完成（内存版验证通过，pgvector路径代码就绪） |
| Phase 3 | BM25 + Dense + Hybrid Fusion | ✅ 完成，已跑真实对比实验 |
| Phase 4 | Reranker | ✅ 完成，已跑真实有无对比实验 |
| Phase 5 | Evaluation（30条评测集 + Retrieval指标） | ✅ 完成，多轮真实数字见 experiment_results.md |
| Phase 6 | Agent Loop + State + Stop Condition | ✅ 完成，真实DeepSeek联调验证 |
| Phase 7 | 4个Tool（KB Search / Log Query / Service Metrics / **Ticket Search**） | ✅ 完成（Ticket Tool是MVP稳定后追加的） |
| Phase 8 | FastAPI收口 + 异常处理 + Structured Logging | ✅ 完成，含不依赖DB的集成测试 |
| Phase 9 | Observability（retrieval_logs/agent_runs全链路） | ✅ 完成（代码就绪，需要真实Postgres环境才能端到端验证落库） |
| Phase 10 | 性能优化 | ⬜ 待开始（已有真实延迟数据：Agent单次Run 30~47秒，见experiment_results.md，尚未优化） |
| Phase 11 | 部署（Docker Compose） | ⬜ 代码就绪，本机因宿主机WSL2虚拟化未开启暂未验证 |

> 说明：本项目全程由AI辅助自动执行搭建，Phase 1-9的骨架代码、mock数据、评测集、单元/集成测试
> 均已完成并跑出真实数字（而非只是"代码写完了"）。受限于本机环境（Docker Desktop因宿主机未开启
> Windows虚拟化功能无法启动），Postgres+pgvector生产路径改用内存版实现完成等价验证，详见
> `docs/experiment_results.md`"运行环境说明"一节。

## 2. 每阶段 Review 清单（每次实现后自查）

- Architecture Review：是否符合 Agent Layer / Retrieval Layer 边界？
- Code Review：重复代码 / 错误处理 / 类型 / 资源泄漏
- Failure Review：这个模块挂了会怎样？
- Performance Review：这里可能是瓶颈吗？
- Interview Review：面试官会怎么追问这段代码？

---

## 3. 故障排查手册

### 3.1 Recall 下降排查树

```
Recall 下降
├─ 确认Evaluation Dataset是否变化 → diff eval_cases.json版本
├─ 确认Query是否变化 → 对比retrieval_logs.query历史记录
├─ Query Rewrite异常？ → 对比rewritten_query与原始query的语义偏差
├─ Chunk是否变化？ → 检查documents.version / chunk_index是否重排
├─ Embedding模型/版本是否变化？ → 检查document_chunks.embedding_version
├─ Dense召回是否正常？ → 直接跑cosine similarity脚本复现单条query
├─ BM25是否召回？ → 检查tsvector分词结果，专业术语是否被切碎
├─ Hybrid融合策略是否正确？ → 对比fusion_candidates与两路candidates的排名
├─ Metadata Filter是否误过滤？ → 打印filter前后候选数量
├─ Reranker是否把正确文档排掉？ → 对比rerank前后ground_truth chunk排名
└─ Context Construction是否丢失？ → 检查final_context是否完整传给LLM
```

| 层级 | 如何观察 | 如何验证 | 如何修复 | Regression Test |
|---|---|---|---|---|
| Chunk | 查document_chunks对应chunk内容 | 人工核对chunk是否切断了关键信息 | 调整chunk_size/overlap，重新ingest | eval_cases里加一条针对该chunk边界的用例 |
| Embedding | 查embedding_version字段 | 对比新旧向量的cosine相似度分布 | 全量重新embed，version+1 | 记录embedding_version在eval_results里 |
| Dense | retrieval_logs.dense_candidates | 单条query手动跑pgvector查询 | 检查索引类型/维度是否匹配 | 加入该query到eval集固定跟踪 |
| BM25 | retrieval_logs.bm25_candidates | 检查tsvector分词是否合理 | 自定义词典/切换分词配置 | 关键词类用例回归 |
| Fusion | 对比fusion前后排名 | 手动用不同RRF常数k重算 | 调整融合权重 | Hybrid vs 单路对比实验复跑 |
| Reranker | rerank_candidates vs fusion_candidates | 检查ground_truth chunk的rerank分数 | 检查reranker模型/prompt | 记录rerank前后排名变化到日志 |

### 3.2 Latency 上升排查树

```
系统变慢
├─ API层排队？ → 查FastAPI worker数/并发请求数
├─ DB查询慢？ → EXPLAIN ANALYZE慢查询，检查索引是否命中
├─ Embedding计算慢？ → 单独计时embed()调用
├─ Dense检索慢？ → 检查HNSW索引参数，向量维度
├─ BM25检索慢？ → 检查GIN索引是否生效
├─ Reranker慢？ → Cross-Encoder是batch还是串行调用
├─ Tool调用慢？ → tool_calls.latency_ms分tool统计
└─ LLM调用慢？ → 区分是网络延迟还是模型生成长度问题
```
定位方法：`agent_runs`记录`total_latency_ms`，`tool_calls`/`retrieval_logs.latency_breakdown`记录分层耗时，公式：
`Total = QueryProcessing + Embedding + Retrieval + Reranker + ToolCalling + LLM + PostProcessing`，逐层加总定位瓶颈。

### 3.3 Hallucination（幻觉）排查树

```
回答幻觉
├─ Retrieval阶段：是否真的召回到相关证据？→ 查retrieval_logs
├─ Evidence阶段：证据是否被正确传给LLM？→ 查最终prompt内容
├─ Prompt阶段：是否明确要求"仅基于证据回答，无证据则拒答"？→ 检查system prompt
├─ Model阶段：LLM是否忽略了指令自由发挥？→ 对比evidence与answer的重合度
└─ Validation阶段：Answer Validator是否被跳过？→ 检查validator是否真的执行了grounding check
```

### 3.4 Agent 无限循环排查树

```
Agent不停止
├─ Tool Description不清晰，Planner重复选同一个Tool？→ 检查tool.description
├─ AgentState.tool_budget是否生效？→ 单测should_stop()
├─ sufficient字段是否被正确解析？→ 检查Planner LLM输出的JSON解析逻辑
├─ Max Iterations是否被检查？→ 单测边界条件iteration==max_iterations
└─ Tool返回结果是否格式异常导致Planner无法判断？→ 检查ToolResult.success字段
```

---

## 4. 20 个潜在故障清单（编号对应 architecture.md 第26节）

1. Recall骤降　2. Reranker误杀正确答案　3. Chunk边界切断关键信息　4. Embedding版本不兼容　5. 向量索引未刷新　6. Metadata Filter过度过滤　7. BM25中文分词切碎术语　8. Hybrid融合权重不合理　9. LLM幻觉　10. Agent无限循环　11. Tool调用超时未处理　12. LLM API 429/500　13. Prompt过长截断　14. Prompt Injection　15. 数据库连接池耗尽　16. N+1查询　17. 评测结果不可复现　18. 多轮对话上下文污染　19. 日志敏感信息泄露　20. 冷启动空索引报错

---

## 5. 50 个高频追问问题（面试自测清单）

见 `docs/architecture.md` 设计过程中讨论内容，完整题库如下（分六类，每类需能连续追问三层）：

**RAG基础**：RAG是什么/Chunk Size怎么定/Overlap作用/Embedding为何表达语义/Cosine vs 欧氏/BM25原理/融合策略/Retriever与Reranker职责区别/Top-K怎么定/为何先Top50再精排

**评测**：Recall@K公式/评测集怎么构建防自证循环/100条够吗/Faithfulness怎么算/LLM-as-judge偏差/Precision-Recall权衡/MRR含义

**排障**：Recall骤降怎么查/Embedding vs Chunk问题怎么区分/Reranker会否误杀/系统变慢怎么查/Agent死循环怎么发现/429怎么处理/幻觉怎么防/知识冲突怎么办

**架构选型**：为何pgvector不用Milvus/1000万数据怎么办/为何不用LangGraph/为何不用Redis/Agent与Chatbot区别/是否算真Agent/为何Cross-Encoder/Metadata Filter误伤场景/多轮上下文怎么管理/为何不做Multi-Agent

**工程系统设计**：100并发瓶颈在哪/连接池怎么配/Tool超时重试策略/限流熔断/trace_id怎么贯穿/token成本怎么控/Embedding升级怎么迁移/如何防Prompt Injection

**极端场景**：问题不在知识库怎么办/"忽略之前指令"怎么防/用户要求危险操作怎么办/知识库为空冷启动/多租户怎么改架构/"这不就是套壳RAG"怎么反驳

---

## 6. ADR（技术决策记录）

### ADR-001: 使用 PostgreSQL+pgvector 而非独立向量数据库
- **Decision**: MVP阶段向量存储使用pgvector扩展
- **Why**: 数据规模（几千~几万chunk）远低于Milvus等专用向量库的性能拐点；单数据库降低运维复杂度
- **Alternatives**: Milvus, Elasticsearch(dense_vector)
- **Trade-offs**: 牺牲了大规模场景下的查询性能优化空间，换取架构简单性
- **When to change**: 向量规模破百万，或实测P95查询延迟超过可接受阈值(如500ms)

### ADR-002: 手写Agent Loop而非LangGraph
- **Decision**: MVP自行实现Agent Loop状态机
- **Why**: 当前流程是线性ReAct循环，手写完全够用；需要对Loop内部机制建立第一性理解
- **Alternatives**: LangGraph, AutoGen
- **Trade-offs**: 复杂分支/并行工具调用场景下手写状态机会变得难维护
- **When to change**: 出现需要"多工具并行+结果合并""子图复用"等复杂编排需求时

### ADR-003: LLM/Embedder Provider可插拔，默认Mock/占位实现
- **Decision**: 定义LLMClient/Embedder抽象接口，默认实现不依赖外部API
- **Why**: 保证代码在无网络/无API Key环境下可测试、可复现、成本为零；符合依赖倒置原则
- **Alternatives**: 直接硬编码调用某个商业API
- **Trade-offs**: 默认Provider语义能力弱，评测数字不能代表生产级效果，必须在报告中明确标注
- **When to change**: 配置真实API Key后通过环境变量切换，接口不变

### ADR-005: KnowledgeSearchTool 对 Reranker 分数做最低阈值过滤（真实运行中发现的问题）
- **Decision**: `RERANKER_MIN_SCORE`（默认0.5）作为证据是否可用的硬阈值，低于阈值的候选不进入Evidence
- **Why**: 离线联调时发现一个真实缺陷——Retrieval本身对任何query都会返回Top-K结果（哪怕全部不相关），
  如果Tool把这些结果原样当作"检索到证据"传给Agent，Validator会误判为"有KB证据"从而不触发Abstention。
  用真实数据验证：相关query的rerank分数集中在0.53~0.70，不相关query（"年假申请流程""K8s怎么配HPA"）
  的分数集中在0.40~0.46，两者有可观察的区间差异，但样本量小（4条），**这个阈值是初步校准，
  不是严格统计意义上的最优值**，后续应该用完整30条评测集做ROC分析进一步校准
- **Alternatives**: 让LLM在生成答案阶段自己判断"这些证据是否相关"（不可靠，LLM对无关证据也可能强行编答案，
  这正是幻觉的来源）；对Reranker做二分类微调输出相关性概率（更准确但需要标注数据和训练成本，MVP阶段不值得）
- **Trade-offs**: 阈值设置过高会误伤真正相关但表述差异大的语义类问题(Recall下降)；设置过低起不到过滤作用。
  这个过滤发生在Tool层而不是Pipeline层——Pipeline的职责是排序，"多相关才算相关"是应用层策略，两者不应该耦合
- **When to change**: 换成真实Embedding模型和真实Cross-Encoder Reranker后，分数分布会完全不同，
  阈值必须重新校准，不能沿用mock_hash/heuristic下标定的0.5

### ADR-006: Planner必须强制先查knowledge_search，不能靠Answer层兜底防幻觉
- **Decision**: 真实LLM Provider的Planner system prompt里加入强制规则——只要没调用过
  knowledge_search就不能判断sufficient=true，即使LLM自己知道问题的通用答案
- **Why**: 接入DeepSeek后的真实运行发现，纯知识类问题（"什么是缓存穿透"）Planner会
  直接用自己的训练知识判断"信息已经足够"，完全跳过knowledge_search。虽然Answer层的
  grounding约束正确地阻止了它编造答案（转为abstained），但这不是我们想要的结果——
  代价是放弃了查证企业知识库的机会。防幻觉应该在"要不要查证据"这一步就做对，
  不能只依赖"编造之前踩刹车"这一层兜底
- **Alternatives**: 保留Answer层兜底作为唯一防线（已验证过，效果是"安全但没利用上知识库"）
- **Trade-offs**: 强制先查会增加至少一次工具调用的延迟和成本，对确定不需要企业知识的
  问题（如"1+1等于几"）也会先去查一次知识库，是有意的过度保守
- **When to change**: 如果Intent分类能够可靠区分"纯通用常识问题"和"可能涉及企业内部
  定义的问题"，可以只对后者强制此规则

### ADR-007: Validator 增加 Evidence Relevance 判断（修复真实bug）
- **Decision**: `validate()` 不再只看"knowledge_search有没有返回evidence"，改成调用
  `llm_client.is_evidence_relevant(query, evidence_texts)`，只有证据被判定为主题相关
  才计入 `has_kb_evidence`
- **Why**: DeepSeek联调发现真实bug——"公司年假申请流程"这个知识库外的问题，
  Reranker返回的payment-service文档分数刚好压线超过0.5阈值，被当成"有证据"，
  导致status误判为answered，即使回答正文里LLM自己说"证据不相关无法回答"。
  纯分数阈值挡不住"分数过线但主题不对"这类情况，需要一次真正的语义相关性判断
- **Alternatives**: 提高RERANKER_MIN_SCORE阈值（治标不治本，阈值提多高都可能有临界案例）；
  让Answer Validator解析LLM生成的答案文本里是否包含"证据不足"字样（脆弱，依赖措辞，
  语言风格一变就失效）
- **Trade-offs**: 真实Provider下每次有KB证据时多一次LLM调用（增加延迟和成本），
  Mock Provider退化成词面重合度启发式（本身也不完美，只是比"完全不检查"好）
- **When to change**: 如果这次调用带来的延迟在生产场景下不可接受，可以考虑把这次判断
  合并进generate_answer的同一次调用里（一次调用里既生成答案又输出relevant字段），
  用结构化输出减少一次往返，当前为了让Validator逻辑独立可测试，先保持两次调用

### ADR-008: 换真实模型后 RERANKER_MIN_SCORE 从 0.5 重新校准为 0.3，且发现Reranker本身效果存疑
- **Decision**: 切换到真实Embedder(`local_st`/`bge-small-zh-v1.5`)和真实Reranker
  (`cross_encoder`/`bge-reranker-base`)后，`RERANKER_MIN_SCORE`从0.5改成0.3（真实
  CrossEncoder分数分布和heuristic reranker完全不是一个量级）
- **Why**: 实测5条真实query的分数分布后校准（见 experiment_results.md），同时**用真实
  模型重跑Reranker有无对比实验后，发现真实Cross-Encoder Reranker在当前评测集上反而让
  Recall/Precision/MRR全面下降**，不是预期中的提升
- **Alternatives**: 保留Reranker但调整候选池大小/精排数量；换更大的Reranker模型
  （bge-reranker-large）；不用Reranker，直接用Fusion结果
- **Trade-offs**: 如实记录了这个反直觉结果而不是回避或"调出一个好看的数字"——当前证据
  不支持"这个场景下Reranker值得用"这个结论，但样本量太小（30条评测集/43个chunk）不能
  证明"Reranker在这类场景下就是没用的"，两者是不同的结论，不能混为一谈
- **When to change**: 知识库规模扩大到几百~几千chunk、评测集扩大到100+条后重新做这组对比，
  如果那时候Reranker仍然是负贡献，才能真正下"这个Reranker在这个场景不适用"的结论

### ADR-004: 不使用Redis
- **Decision**: MVP不引入缓存层
- **Why**: 没有实测出的缓存收益场景，提前引入是过度工程化
- **Alternatives**: 引入Redis缓存embedding/检索结果
- **Trade-offs**: 重复query会重复计算，但当前QPS量级下影响可忽略
- **When to change**: 压测发现同一query/embedding高频重复请求且计算成本可观时
