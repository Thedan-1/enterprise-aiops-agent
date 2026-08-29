# Contributing

1. Create a branch; do not commit directly to `main`.
2. Keep tools narrow and read-only unless a separate threat review justifies a write action.
3. Add tests for authorization, tenant scope and failure behavior when changing Agent or Tool code.
4. Run `python eval/validate_dataset.py` and `pytest tests -q`.
5. Do not claim an experiment improved quality unless the raw result is committed under `eval/results/`.

