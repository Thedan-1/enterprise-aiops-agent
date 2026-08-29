from eval.validate_dataset import validate


def test_v2_evaluation_dataset_quality_gate():
    report = validate()
    assert report["cases"] >= 100
    assert report["documents"] >= 25
    assert report["categories"]["not_in_kb"] >= 10

