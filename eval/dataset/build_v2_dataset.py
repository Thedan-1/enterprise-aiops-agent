"""Deterministically expand the hand-written 30-case baseline to 100 V2 cases."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "eval_cases.json"

TOPICS = [
    ("kafka_consumer_lag", "Kafka消费积压", ["consumer lag持续上升怎么排查", "为什么增加消费者后Kafka积压没有改善", "毒消息如何造成消费积压", "Kafka rebalance频繁会带来什么影响"]),
    ("kubernetes_pod_restart", "Pod重启", ["Pod的restartCount持续增加怎么查", "Kubernetes OOMKilled应该看哪些指标", "liveness probe导致容器重启怎么判断", "提高memory limit为什么不一定能解决重启"]),
    ("kubernetes_pending_pod", "Pod Pending", ["Pod一直Pending怎么排查", "调度器提示Insufficient memory是什么意思", "PVC未绑定为什么会导致Pod Pending", "nodeSelector配置错误如何定位"]),
    ("deployment_rollback_sop", "发布回滚", ["发布后错误率升高应该如何回滚", "数据库变更不向后兼容时能直接回滚应用吗", "回滚前要保留哪些证据", "回滚后需要验证哪些业务指标"]),
    ("grpc_timeout", "gRPC超时", ["gRPC DEADLINE_EXCEEDED是什么意思", "如何定位gRPC调用哪一段慢", "为什么增加deadline不一定能解决超时", "gRPC重试怎样避免请求风暴"]),
    ("dns_resolution_failure", "DNS故障", ["服务日志出现NXDOMAIN怎么排查", "只有一个节点DNS解析失败怎么办", "CoreDNS延迟高会造成什么现象", "为什么不建议把服务IP写死"]),
    ("tls_certificate_expiry", "TLS证书", ["certificate has expired怎么处理", "证书更新后为什么服务仍使用旧证书", "TLS主机名不匹配怎么排查", "如何设计证书到期告警"]),
    ("database_replication_lag", "复制延迟", ["PostgreSQL只读副本返回旧数据怎么查", "WAL生成过快为什么会增加复制延迟", "业务要求写后立刻读应该访问主库还是副本", "备库磁盘慢如何影响replay lag"]),
    ("database_deadlock", "数据库死锁", ["数据库发生deadlock应该收集什么", "不同锁顺序为什么会死锁", "死锁能不能靠无限重试解决", "如何缩小数据库锁范围"]),
    ("slow_query_sop", "慢查询", ["如何从大量慢SQL里找到优化重点", "EXPLAIN ANALYZE生产执行有什么风险", "N+1查询为什么会拖慢接口", "索引是不是越多越好"]),
    ("redis_hot_key", "Redis热Key", ["Redis某个分片CPU特别高怎么查", "如何安全定位Redis热Key", "热Key拆分解决什么问题", "本地缓存热Key要注意哪些风险"]),
    ("redis_eviction", "Redis淘汰", ["Redis evicted_keys持续增长说明什么", "maxmemory-policy怎么影响数据淘汰", "大Key如何导致Redis内存压力", "为什么只扩Redis内存可能还会复发"]),
    ("thread_pool_exhaustion", "线程池耗尽", ["CPU不高但接口大量超时可能是线程池吗", "线程池队列持续增长怎么定位", "盲目扩大线程池有什么风险", "下游变慢如何拖垮上游线程池"]),
    ("disk_full", "磁盘容量", ["磁盘满会导致哪些服务异常", "空间没满但inode满了怎么排查", "删除日志后磁盘空间为什么没释放", "生产磁盘告警后的安全处理顺序"]),
    ("api_rate_limit", "API限流", ["HTTP 429应该怎么处理", "Retry-After头有什么作用", "指数退避为什么需要随机抖动", "提高API限额前为什么要检查下游容量"]),
    ("clock_skew", "时钟漂移", ["Token莫名提前过期可能和时钟有关吗", "系统时钟漂移为什么影响TLS", "分布式日志时间线混乱怎么排查", "为什么不建议手工大幅调整生产节点时间"]),
]

OUT_OF_SCOPE = [
    "公司今年年假有多少天", "食堂今天午餐是什么", "如何申请办公用品", "销售部门本季度目标是多少",
    "给我推荐一部电影", "财务报销需要谁审批",
]


def main() -> None:
    cases = json.loads(TARGET.read_text(encoding="utf-8"))[:30]
    next_id = 31
    for slug, label, questions in TOPICS:
        for index, question in enumerate(questions):
            cases.append({
                "id": f"eval_{next_id:03d}",
                "question": question,
                "category": "keyword" if index == 0 else "semantic",
                "difficulty": "easy" if index == 0 else "medium",
                "ground_truth_doc_slugs": [slug],
                "expected_answer_contains": [label.split("故障")[0]],
            })
            next_id += 1
    for question in OUT_OF_SCOPE:
        cases.append({
            "id": f"eval_{next_id:03d}", "question": question, "category": "not_in_kb",
            "difficulty": "hard", "ground_truth_doc_slugs": [], "expected_answer_contains": ["证据不足"],
        })
        next_id += 1
    assert len(cases) == 100
    TARGET.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

