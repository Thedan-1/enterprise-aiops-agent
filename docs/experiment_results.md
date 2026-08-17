# 实验结果记录（真实运行，非编造）

运行时间：2026-08-17
运行方式：`python scripts/offline_demo.py`（离线内存版Pipeline，原因见下方"运行环境说明"）
Provider：`EMBEDDER=mock_hash RERANKER=heuristic LLM=mock`（占位实现，见下方"如何解读这些数字"）
数据：9篇原创mock文档，chunk_size=512时切成43个chunk；30条评测集（10关键词/10语义/5多证据/5知识库外）

## 运行环境说明（重要，如实记录）

本次开发环境的 Docker Desktop 无法启动——诊断发现是宿主机未开启 Windows 的
"Virtual Machine Platform" 功能，导致 WSL2 报错
`WSL_E_VIRTUAL_MACHINE_PLATFORM_REQUIRED`。这需要管理员权限执行
`dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart`
并重启机器才能修复，属于系统级设置变更，自动化流程里不做这件事。

为了不在这个限制前空等，把 `RetrievalPipeline` 的 Dense 检索改成了依赖注入
（`app/rag/pipeline.py`），额外实现了 `InMemoryDenseRetriever`
（`app/rag/retriever/in_memory_dense.py`，cosine similarity 的内存版实现，
排序逻辑和数据库版本完全等价，区别只在于大数据量下数据库版本能用HNSW索引），
本次所有实验都跑在这个内存版本上。Postgres+pgvector 生产路径代码已实现
（`app/rag/retriever/dense.py` + `app/db/`），等宿主机开启虚拟化后可直接切换，
不需要改 Pipeline 逻辑——这正是当初把 Dense Retriever 设计成可注入接口的原因。

## 如何解读这些数字（避免误读，评测报告的免责声明）

- **Embedder = mock_hash**：字符n-gram hashing，本质是"词面重合度"的向量化，
  对关键词类查询有效，对纯语义改写能力弱。这意味着下面 semantic 类别的 Recall
  可能被低估或被巧合的字面重合高估，**不能代表真实 Embedding 模型（如
  bge-large-zh/text-embedding-3）的效果**。
- **Reranker = heuristic**：词面重合度打分，不是Cross-Encoder，排序精度弱于真实Reranker。
- **LLM = mock**：规则引擎，Agent Loop的工具选择顺序是硬编码规则而不是真实推理，
  Answer的文字内容是模板拼接，不能评价"回答质量"，只能验证"流程和状态机是否正确"。
- **30条是方向性验证，不是统计显著结论**（尤其 not_in_kb 只有5条，见 architecture.md 第0节）。

## 实验1：Chunk Size 对比（256 / 512 / 1024，overlap=50）

| chunk_size | n_chunks | Recall@5 | Precision@5 | MRR |
|---|---|---|---|---|
| 256 | 47 | 0.8533 | 0.3789 | 0.72 |
| 512 | 43 | 0.8933 | 0.3539 | 0.7533 |
| 1024 | 42 | 0.8933 | 0.3594 | 0.7533 |

**观察**：512和1024的Recall/MRR明显高于256，512和1024之间几乎没有差异。
**可能原因（待更大数据量验证，当前9篇文档、43个chunk的样本量下这个结论的置信度有限）**：
256在我们的文档结构下容易把一个小节内"问题现象"和"解决方案"切到两个不同chunk里，
导致检索到其中一个chunk时命中的信息不完整；文档普遍不长，512和1024对多数section
而言效果相当于"整节不切"，所以两者接近。**这不是"512就是最优值"的通用结论**，
是这批文档在这个规模下的观察，文档变长/变多后需要重新做这个实验。

## 实验3：Dense-only / BM25-only / Hybrid 对比

评测口径：候选池（Top30）直接算指标，不经过Reranker，目的是隔离"检索策略"这一个变量。

| 策略 | Recall | Precision | MRR |
|---|---|---|---|
| Dense-only | 1.0 | 0.1389 | 0.769 |
| BM25-only | 1.0 | 0.1681 | 0.8867 |
| Hybrid(RRF) | 1.0 | 0.1384 | 0.7633 |

**观察（和预期不完全一致，如实记录，不回避）**：在当前极小的知识库规模下（9篇文档），
三种策略的 Recall 都是满分——候选池给到Top30，而知识库总共只有43个chunk，几乎是
"捞尽全库"，Recall差异被这个规模效应盖住了，看不出真实的召回能力差异。反而是
**BM25-only 的 MRR（0.8867）比 Hybrid（0.7633）更高**，这与"Hybrid应该更好"的
直觉预期相反。初步分析：mock_hash Embedder的语义表达能力弱，Dense通道引入的排序
噪声在小样本下拉低了融合后的排名质量，RRF按排名而非分数融合，Dense召回到的
"伪相关"结果如果排名靠前会拖累BM25本来能排到第一的正确答案。

**结论**：**这组数据不能用来证明"Hybrid比单路好"**——现有条件下(知识库太小/
Embedder是占位实现)得出的是相反的信号，如实报告，不能因为"Hybrid理论上应该赢"
就选择性忽略这个结果。这个实验需要在真实Embedding模型 + 更大知识库规模下重跑，
当前唯一站得住的结论是："候选池覆盖了几乎全部知识库时，检索策略的差异会被规模
效应掩盖，等未来接入真实文档做到几千chunk规模，再重跑这组实验才有意义。"

## 联调发现并修复的真实问题：Abstention 起初完全不生效

跑 Agent Demo时发现：查询"公司的年假申请流程是什么"（知识库完全不包含的问题），
Agent 仍然返回了"answered"状态、生成了看似正常的回答，而不是按设计应该拒答。

**根因**：Retrieval 对任何 query 都会返回 Top-K 排序结果（哪怕全部不相关），
`KnowledgeSearchTool` 原来直接把这些结果全部当作"证据"传给下游，`Validator` 只
检查"有没有 evidence"而不检查"evidence 是否真的相关"，导致误判为"有知识库证据"。

**修复**：在 `KnowledgeSearchTool` 里加了 Reranker 分数阈值过滤（`RERANKER_MIN_SCORE=0.5`），
低于阈值的候选不计入Evidence。阈值是用4个真实query（2个相关+2个不相关）观察到的
分数分布校准的（相关query集中在0.53~0.70，不相关query集中在0.40~0.46），
**样本量很小，是初步校准值，不是严格调参结果**，完整方法和已知局限见
`docs/project_management.md` ADR-005。

修复后重跑Agent Demo：`公司的年假申请流程是什么` → `status=abstained, confidence=0.1`，
正确拒答。这是本次真实运行揪出来的一个属于"防幻觉设计"范畴的真实缺陷，
不是提前预设好的演示——这个过程本身就是很好的面试素材（见50题清单里
"知识库没有答案时Agent怎么办"这一题，现在有真实的bug发现+修复故事可以讲）。

## 接入真实 LLM（DeepSeek）后的验证（2026-08-17 补充）

用户提供了 DeepSeek API Key，接入后（`LLM_PROVIDER=deepseek`，走 OpenAI 兼容REST接口，
`app/core/llm_client.py` 新增 `DeepSeekLLMClient`），重跑了 Agent Demo 的3个query，
Embedder/Reranker仍是占位实现（这两个和LLM是独立的Provider）。

**第一轮真实LLM运行暴露的问题**：真实LLM的Planner不像MockLLM那样被硬编码"第一步必须
查知识库"，而是会自己判断。结果是：① 诊断类query（订单502）跑到了 `timeout`（30秒内
没收敛，一直在追加工具调用）；② 纯知识类query（"什么是缓存穿透"）Planner第一步就判断
`sufficient=true`、**完全没有调用knowledge_search**——这是一个真实的、有代表性的问题：
LLM自己"知道"缓存穿透的通用定义，倾向于直接从自己的训练知识回答，而不是先查企业知识库。
好消息是下游的 Answer Validator 起了作用：因为没有Evidence，`generate_answer`的system
prompt强制"只能基于提供的证据回答"，DeepSeek老实地回答了"证据不足"而不是凭自己知识编，
最终状态正确地判成了 `abstained`——**说明"防幻觉"这道保险生效了，但保险生效的代价是
放弃了利用真实企业知识库的机会，这不是我们想要的行为，问题出在Planner层，不该靠
Answer层兜底**。

**修复**：给 Planner 的 system prompt 加了强制规则："只要没调用过knowledge_search就不能
判断sufficient=true，哪怕LLM自己知道通用定义，因为企业内部实现可能不同"；同时把
`AGENT_TIMEOUT_S` 从30调到45（真实API往返比MockLLM慢，30秒对多轮工具调用偏紧）。

**修复后重跑，三个query的结果**：
1. **"order-service 502"**（诊断类）：3轮收敛（`knowledge_search`→`service_metrics`→
   `log_query`），`status=answered, confidence=1.0`。回答质量和MockLLM完全不是一个量级——
   准确复现了历史case里"第三方网关抖动→payment-service重试放大延迟→order-service连接池
   耗尽→502"这条级联链路，明确区分"已确认信息"和"待排查项"，给出可执行的排查步骤，
   结论用"最可能的根因是..."这种恰当的不确定性措辞，而不是拍胸脯下结论。这是真实LLM
   推理和Mock规则引擎的能力差距的直接证据。
2. **"什么是缓存穿透"**（知识类）：正确调用了`knowledge_search`，基于Redis故障文档给出
   准确定义，还主动区分了穿透/击穿/雪崩三个概念避免混淆，`status=answered, confidence=0.65`。
3. **"公司年假申请流程"**（知识库外）：**这里又暴露了一个新问题，如实记录**——
   `knowledge_search`被连续调用了2次（打满tool_budget强制停止），返回的1条"证据"其实是
   payment-service接口文档（reranker分数刚好压线超过0.5阈值，但内容和年假完全无关），
   所以最终 `status` 判成了 `answered` 而不是 `abstained`——尽管LLM在**回答正文里**正确
   识别出"该证据与年假申请无关，无法回答"。**这说明目前的 Abstention 判断（Validator只看
   "有没有及格分数的evidence"）还是太粗糙**：分数刚过阈值但主题完全不相关的证据，
   会让status字段和回答内容对不上。更彻底的修法应该是让Validator也做一次"证据和问题
   主题相关性"的语义校验（比如让LLM自己判断"这些证据能不能支持回答这个问题"作为
   Answer Validator的一部分，而不是单纯依赖Reranker分数阈值），这是下一步要做的，
   本次先如实记录这个已知局限，没有为了让demo好看而回避。

## 尚未完成的实验（诚实标注，不伪造）

- Reranker有无对比（当前Reranker默认开启，还没跑"关闭Reranker"的对照组）
- Max Iterations对Task Success Rate的影响
- 真实Embedding模型（非mock_hash）下重跑全部实验——这是最重要的后续验证，
  因为当前所有"看起来合理"的结论都建立在占位Embedder之上
