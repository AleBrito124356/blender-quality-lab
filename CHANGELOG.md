# Changelog

## 0.2.0 - 2026-09-23

### Added

- **Inspection schema 2** (`inspect`), computed from geometry so models without vision can use it:
  - true render visibility and evaluated geometry;
  - each object's share of the frame, cut-off edges and occlusion, plus an object-ID grid of the frame;
  - the subject, with `--subject` / `--subject-collection` to choose it;
  - contact groups and floating gaps;
  - light reach after shadow rays, irradiance estimates and key-to-fill;
  - material facts;
  - animation through the Blender 5 layered-action API, with sampled motion.
- v2 gates with `blocked_by` dependencies, advisory warnings and `score --strict-contact`.
- `measure`: a dependency-free PNG decoder and exposure/layout metrics.
- `describe`: a Markdown/JSON report with an ASCII object map and prioritized fixes that carry Blender Python.
- `check`: inspect, preview render, measure, score and report in one isolated Blender run. `inspect --preview` renders the preview alone.
- `doctor`: shows the Blender that will be used, how it was found and its version.
- `briefs list|show|validate`. The briefs now ship inside the package.
- `diff`: before/after scene comparison with an objective preserve-and-relight verdict (`--original` proves the input was not overwritten).
- `summarize`: aggregates `runs/<config>/<brief>/<run>/`, reading Astra manifests, without a combined rank.
- `examples/runs`, generated from real offline Blender runs by `examples/make_example_runs.py`.
- Blender integration tests (`pytest -m blender`) and fixtures recorded from Blender 5.2.1.

### Changed (behaviour)

- Every Blender process, `inspect` included, now runs with `--background --factory-startup --disable-autoexec`, and user/site script overrides are removed from its environment. Before, `inspect` loaded the user's add-ons and startup file.
- Blender is found through `--blender`, then `$BLENDER`, then PATH, then the standard install folders. Before, only PATH was used.
- `build` and `inspect` capture Blender's log and print only the output paths. Use `--verbose` to see the log.
- Errors print one line (plus the tail of Blender's output) instead of a Python traceback. Exit code 2 means invalid input; exit code 1 means Blender or a gate failed.
- `inspect` writes schema 2. `score` still accepts schema 1 files and scores them exactly as before; reports scored from schema 2 have `schema_version: 2`, `detail`, `blocked_by` and `warnings`.
- `review` rejects the `YOUR_NAME` placeholder and explains null scores.
- `briefs.json` moved from the repository root to `src/blender_quality/data/briefs.json`. Briefs gained the optional fields `subject_collection`, `strict_contact` and `diff`.
- Recipes:
  - the factory scene and unused datablocks are removed before saving;
  - `use_nodes` is only set before Blender 5.0 (no more deprecation warnings on 5.x);
  - the backdrop floor's top is at z = 0 (it was 1.5 cm below the plinths);
  - the interior shelves are flush with the wall (they hovered 5 cm off it);
  - the interior edge light was raised to clear the back wall, which had blocked it completely.

  The reference renders in `docs/` were re-rendered with Blender 5.2.1.

### Deprecated

- `compare`: use `summarize RUNS_DIR`. `compare` still lists scored reports and forwards a runs folder to `summarize`.
