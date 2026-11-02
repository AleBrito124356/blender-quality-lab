# Changelog

## 0.3.0 - 2026-11-02

### Added

- **Blender without an install.** Every Blender command (`build`, `inspect`, `check`, previews, `pytest -m blender`) also runs through a Python interpreter that can import Blender's `bpy` module from PyPI. `scripts/bpy_launcher.py`, run with `python -I`, accepts exactly the isolated Blender command line and emulates it:
  - per-user Blender folders point at an empty temporary folder before `bpy` is imported;
  - autoexec is disabled before the file is opened with `load_ui=False, use_scripts=False`;
  - `sys.argv` is Blender-style, and a script exception exits with code 1;
  - a file that cannot be read stops the run.
- Discovery: `--blender` and `$BLENDER` accept a Blender executable, its folder or a Python interpreter. After PATH and the install folders come `$BLENDER_PYTHON` and then the current interpreter if it can import `bpy`. A path's kind comes from its name, or from a `--version` probe. `doctor` reports the kind (`Blender executable` or `bpy module in a Python interpreter`).
- **Stable integration API** `blender_quality.api` (`API_VERSION = 1`): `check`, `live_inspection_code`, `parse_live_output`, `score`, `describe`, `measure`, `schema`, `schema_path`, `blender_info`.
- **Live inspection**: Python source that inspects the current scene of an already running Blender, for example through Blender MCP's `execute_code`. It prints one `BQL_INSPECTION_JSON:` line, opens no file, never saves, and restores the viewport visibility and frame it changes. Also available as `blender-quality live-code`.
- `check --json` prints the report JSON and nothing else on stdout. `report.json` holds the same report: the `describe` report plus `all_gates_passed`, every gate under `checks`, the Markdown text, the written files and the Blender runtime.
- JSON Schemas (draft 2020-12) for inspection schema 2 and the report, shipped in the wheel under `blender_quality/schemas/`; the tests validate the recorded fixtures and the reports generated from them.
- `inspector.mode` (`file` or `live`) in new inspections; live inspections add `unsaved_changes` and `context_mode`.
- GitHub Action (`action.yml`): installs bpy from PyPI and checks every matching `.blend`. It adds the reports to the job summary and annotates failed gates. In strict mode it fails when a gate fails.
- `.github/workflows/ci.yml`: lint, offline tests and build on Linux and Windows; Blender integration tests through bpy 5.2.3 and 4.5 from PyPI; the action run on two recipe scenes. It replaces the template in `docs/github-actions.yml`.
- Agent skill `skills/blender-quality/SKILL.md`: the check, fix, re-check loop, choosing the subject, and the limits of the gates.
- Integration tests for isolation on either kind, each with a control run that shows the planted code fires when isolation is off: user startup scripts, `BLENDER_SYSTEM_SCRIPTS`, a registered text block and a scripted driver in the `.blend`. Further tests cover script exceptions, `SystemExit`, the timeout, unreadable files, the live inspection against `inspect`, and `api.check` end to end.

### Fixed

- A failed `check` left the previous run's `technical.json`, `report.md` and `report.json` in the output folder, so a harness reading `report.json` after an error got a stale report. All five output files are now removed before the run.
- `check` of a missing scene created an empty `SCENE.quality/` folder before failing.
- The environment scrub missed `BLENDER_USER_RESOURCES` and `BLENDER_SYSTEM_RESOURCES` (Blender 4.2+), which relocate the folders startup scripts load from. It also missed `BLENDER_SYSTEM_PYTHON`, which swaps the bundled Python library, and the `*_DATAFILES` overrides.
- The inspector's animation sampling did not restore the current frame if it failed part-way; it now restores the frame and subframe in all cases.

### Changed (behaviour)

- A Python interpreter passed as `--blender` is now run as a bpy interpreter. Before, it was started with Blender's flags and failed. A Python that cannot import `bpy` gives a `BlenderNotFound` error that explains how to install it.
- Error messages name the runtime: `Blender (bpy module) exited with code 1 while running inspect_scene.py`.
- The bpy launcher ends its process without bpy's native shutdown. bpy 4.5 can hang forever in a C++ static destructor after a scripted driver failed to evaluate, which every inspection of a file with a Python driver triggers. The launcher runs the Python exit handlers, removes Blender's session temp folder, flushes output and exits.
- `report.json` is now the full check report (a superset of the previous `describe` report). `check --format json` prints the same thing as `--json`.
- Blender 4.5 LTS is verified again: the whole integration suite passes through bpy 4.5.15.

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
- `check`: inspect, preview render, measure, score and report in one isolated Blender run. `inspect --preview` renders the preview alone. A scene that cannot render still gets its inspection and report; the preview records why it was skipped.
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
