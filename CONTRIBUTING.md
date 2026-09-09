# Contributing

Add original, deterministic recipes and cite any third-party asset licenses. Prefer procedural assets that require no downloads. Every recipe should create a new scene, use named objects/materials and expose camera/lighting choices.

Keep technical facts and subjective aesthetic judgments separate. New technical checks must document their false positives/negatives and include tests. A model leaderboard requires matched briefs, budgets, settings, multiple runs and preserved failures; do not submit cherry-picked examples as benchmark results.

Run pytest, Ruff and the wheel build. For Blender scripts, also build/render in a disposable Blender process and record its version.
