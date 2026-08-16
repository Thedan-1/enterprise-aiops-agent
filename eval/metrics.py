"""Retrieval 评测指标：Recall@K / Precision@K / MRR。

Ground truth 的粒度说明（重要，评测报告必须如实标注）：evaluation_cases 里的
ground_truth 是"文档级别"（doc_slug），不是chunk级别。原因：chunk的切分边界
会随chunk_size/overlap实验变化而变化，chunk级别的ground truth在做chunking
对比实验时会失效，文档级别对chunk策略变化更鲁棒。代价是：这组指标衡量的是
"有没有从正确的文档里捞到至少一个chunk"，比真正的chunk级Recall更宽松，
不能等价于生产系统里"chunk粒度的精确Recall"。
"""


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def recall_at_k(retrieved_slugs: list[str], ground_truth_slugs: list[str]) -> float | None:
    if not ground_truth_slugs:
        return None  # not_in_kb类用例不适用Recall，需要单独用Abstention Rate衡量
    gt = set(ground_truth_slugs)
    hit = len(set(retrieved_slugs) & gt)
    return hit / len(gt)


def precision_at_k(retrieved_slugs: list[str], ground_truth_slugs: list[str]) -> float | None:
    deduped = _dedupe_preserve_order(retrieved_slugs)
    if not deduped:
        return 0.0
    gt = set(ground_truth_slugs)
    hit = len(set(deduped) & gt)
    return hit / len(deduped)


def mrr(retrieved_slugs: list[str], ground_truth_slugs: list[str]) -> float | None:
    if not ground_truth_slugs:
        return None
    gt = set(ground_truth_slugs)
    for i, slug in enumerate(_dedupe_preserve_order(retrieved_slugs)):
        if slug in gt:
            return 1.0 / (i + 1)
    return 0.0
