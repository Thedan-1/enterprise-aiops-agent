# V2 验收结果

运行日期：2026-08-30。所有数字来自仓库内保存的运行结果，不是估算值。

## 数据规模

- 原创企业运维文档：25 篇（V1 为 9）。
- Chunk：66 个（chunk_size=512）。
- 评测问题：100 条（V1 为 30）。
- 分布：关键词 26、语义 58、多证据 5、知识库外 11。

## 100 条 Retrieval 基线

| 指标 | 结果 |
|---|---:|
| Recall@5 | 0.9363 |
| Precision@5 | 0.2418 |
| MRR | 0.8830 |
| 关键词 Recall | 0.9615 |
| 语义 Recall | 0.9483 |
| 多证据 Recall | 0.6667 |

解读：召回与首个正确结果排名较好，多证据问题仍是弱项。Precision 使用文档级 ground truth 评估 chunk 级结果，同一正确文档的多个 chunk 会被重复惩罚，因此不能单独用 0.2418 判断答案质量。知识库外问题在检索阶段仍会返回 Top-K，拒答依赖后续分数阈值和 Evidence Validation。

原始结果：`eval/results/v2_retrieval_*.json`。

## Retrieval 延迟

真实本地 BGE Embedder + Cross-Encoder，模型加载时间排除：

| 场景 | 平均 | P95 |
|---|---:|---:|
| 首次检索 | 2159 ms | 2984 ms |
| 相同问题缓存命中 | 0.27 ms | 0.35 ms |

缓存只优化相同 query 的重复查询；它不解决首次检索，也不解决 Agent 多轮 DeepSeek API 调用。缓存位于单进程内存，进程重启会丢失，多实例间不共享。

## 安全与隔离

- 签名登录 Token、过期校验和篡改测试。
- operator/viewer/auditor 三种角色；工具权限由代码白名单决定。
- alpha/beta 两个演示租户使用不同 Retrieval Runtime，检索前完成数据隔离。
- 直接 Prompt Injection、超长输入和用户级限流。
- 登录、聊天、阻断和限流写入审计日志；审计员只能读取本租户记录。
- 工具全部只读，没有重启、删除或配置修改能力。

## 仍未达到生产要求

- 本地认证不是企业 OIDC，JSONL 审计也不是不可篡改日志平台。
- PostgreSQL/pgvector 与 Row Level Security 尚未在本机 Docker 环境验证。
- 文档和评测仍由项目作者构造，不能替代真实 SRE 标注集。
- 多证据检索、首次检索延迟和 LLM 串行调用仍需优化。

