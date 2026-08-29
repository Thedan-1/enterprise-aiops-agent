# V2 项目状态

当前分支：`codex/v2-production-hardening`

| 工作流 | 状态 | 交付物 |
|---|---|---|
| Roadmap 与验收标准 | 完成 | `roadmap/V2_ROADMAP.md` |
| 知识库与评测集扩充 | 完成一轮，继续评估 | 29 docs / 110 cases / quality gate |
| 身份、权限、多租户 | 完成（演示路径） | signed token / RBAC / isolated runtimes |
| 安全与审计 | 完成（演示路径） | guard / limiter / JSONL audit / threat model |
| 延迟基线与优化 | 完成 | cold/warm benchmark + TTL/LRU cache |
| GitHub 公开交付 | 进行中（CI 外部阻塞） | public repo / PR #1；README 已重构并加入真实运行截图 |

## V2 实际结果

- 110-case Recall@5：0.9209；MRR：0.8754；多证据 Recall：0.7444。
- 29 文档 Retrieval 小样本基准：冷查询平均 1635.8ms / P95 1732.9ms；重复 query 缓存命中平均 0.243ms。
- 自动化测试：66 个通过（发布前仍以最终 CI 数量为准）。
- 已验证：401 未登录、403 越权审计、审计员 tenant scope、Prompt Injection 阻断、正常问答。
- 真实浏览器回归：中文“订单服务”可规范化为 `order-service`，真实模型完成 3 次工具调用并形成证据链。
- 可靠性回归：日志工具明确区分“未知服务”和“已知服务无错误日志”，避免把无数据误报为正常；工单工具复用服务别名。
- 知识扩充实验：新增 4 篇官方资料驱动的原创 Runbook 和 10 条多证据题；多证据 Recall 由 0.6667 升至 0.7444，但总体 Recall 由 0.9363 降至 0.9209。

## 外部阻塞

GitHub Actions run `33267197127` 没有进入 checkout 或 test 阶段。GitHub 返回：账户因 billing issue 被锁定，job 未启动。代码侧无法修复；账户解锁后对 PR 重新运行工作流即可。

## 每次提交前检查

- `git status` 不包含 `.env`、日志、模型缓存和个人数据。
- 单元、集成、安全测试全部通过。
- 任何效果或性能数字都必须对应保存的运行结果。
- 新能力同步更新限制清单，避免把模拟能力写成生产能力。
