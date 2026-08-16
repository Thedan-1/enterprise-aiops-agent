from eval.metrics import mrr, precision_at_k, recall_at_k


def test_recall_full_hit():
    assert recall_at_k(["a", "b", "c"], ["a", "b"]) == 1.0


def test_recall_partial_hit():
    assert recall_at_k(["a", "x", "y"], ["a", "b"]) == 0.5


def test_recall_none_when_no_ground_truth():
    assert recall_at_k(["a"], []) is None


def test_precision_counts_unique_retrieved():
    # a出现两次(比如两个chunk来自同一文档)，precision按去重后的文档数算
    assert precision_at_k(["a", "a", "b"], ["a"]) == 0.5


def test_mrr_rewards_earlier_hit():
    assert mrr(["x", "a", "b"], ["a"]) == 0.5
    assert mrr(["a", "x", "b"], ["a"]) == 1.0


def test_mrr_zero_when_not_found():
    assert mrr(["x", "y"], ["a"]) == 0.0
