# V2 项目状态

当前分支：`codex/v2-production-hardening`

| 工作流 | 状态 | 交付物 |
|---|---|---|
| Roadmap 与验收标准 | 完成 | `roadmap/V2_ROADMAP.md` |
| 知识库与评测集扩充 | 完成 | 25 docs / 100 cases / quality gate |
| 身份、权限、多租户 | 完成（演示路径） | signed token / RBAC / isolated runtimes |
| 安全与审计 | 完成（演示路径） | guard / limiter / JSONL audit / threat model |
| 延迟基线与优化 | 完成 | cold/warm benchmark + TTL/LRU cache |
| GitHub 公开交付 | 进行中 | CI / security policy / PR |

## V2 实际结果

- 100-case Recall@5：0.9363；MRR：0.8830；多证据 Recall：0.6667。
- 首次 Retrieval 平均：2159ms；重复 query 缓存命中平均：0.27ms。
- 自动化测试：58 个通过（发布前仍以最终 CI 数量为准）。
- 已验证：401 未登录、403 越权审计、审计员 tenant scope、Prompt Injection 阻断、正常问答。

## 每次提交前检查

- `git status` 不包含 `.env`、日志、模型缓存和个人数据。
- 单元、集成、安全测试全部通过。
- 任何效果或性能数字都必须对应保存的运行结果。
- 新能力同步更新限制清单，避免把模拟能力写成生产能力。
