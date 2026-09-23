# Contributing

Add original, deterministic recipes and cite any third-party asset licenses. Prefer procedural assets that require no downloads. Every recipe should create a new scene, use named objects/materials and expose camera/lighting choices. A new recipe should pass `blender-quality check --strict --strict-contact`.

Keep technical facts and subjective aesthetic judgments separate. New technical checks must document their false positives/negatives in the README gate table and include tests:
- a pure-Python test on a recorded inspection in `tests/fixtures`;
- where the check reads Blender data, a variant in `tests/blender/sabotage.py` that it catches in `pytest -m blender`.

A model leaderboard requires matched briefs, budgets, settings, multiple runs and preserved failures; do not submit cherry-picked examples as benchmark results.

Before sending a change, run:
- `python -m pytest`;
- `python -m pytest -m blender` if Blender is installed (`BQL_UPDATE_FIXTURES=1` re-records fixtures, `BQL_UPDATE_SNAPSHOTS=1` accepts intended report wording changes);
- `ruff check` and `ruff format --check`;
- `python -m build`.

Record the Blender version you verified with in `docs/validation.md`.
