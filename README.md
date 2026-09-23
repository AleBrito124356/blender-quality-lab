# Blender Quality Lab

**Make 3D quality review repeatable, visible and honest.**

A companion to [Astra Blender Harness](https://github.com/AleBrito124356/astra-blender-harness), useful on its own: three executable Blender scene recipes, six controlled briefs, a read-only scene inspector, technical gates and a human visual rubric. No model API or paid asset service is required.

![Reference scene rendered with Blender](docs/abstract.png)

This image is from the deterministic **abstract** recipe rendered with Blender, not an AI quality benchmark.

## Quick start

Python 3.11+ and Blender 4.5+ are required for building/inspecting scenes (verified with 4.5 LTS and 5.2.1 LTS). Scoring JSON reports only requires Python.

```sh
git clone https://github.com/AleBrito124356/blender-quality-lab.git
cd blender-quality-lab
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
blender-quality doctor                      # which Blender will be used, and its version
blender-quality build abstract --output output/abstract --render
blender-quality inspect output/abstract/abstract.blend --output output/inspection.json
blender-quality score output/inspection.json --strict
```

Blender is found in this order: `--blender PATH`, the `BLENDER` environment variable, `blender` on PATH, then the standard install folders (`C:\Program Files\Blender Foundation\Blender *\blender.exe` on Windows, `/Applications/Blender*.app` on macOS, `/usr/bin`, `/usr/local/bin`, `/snap/bin` and `/opt/blender*` on Linux), preferring the highest version. `--blender` also accepts an install folder.

Every Blender process is started with `--background --factory-startup --disable-autoexec`: your add-ons, startup file and preferences are not loaded, and Python embedded in a `.blend` (registered text blocks, scripted drivers) never runs. `BLENDER_USER_SCRIPTS`/`BLENDER_SYSTEM_SCRIPTS`-style overrides are removed from its environment. `--timeout SECONDS` (default 600) stops a stuck process. Failures print one error line plus the last lines of Blender's output, never a Python traceback; exit code 1 means Blender or a gate failed, 2 means the input was invalid. Renders use Cycles CPU at 960 × 720, 32 samples and denoising. A failed build may leave partial output; inspect it and select a new output directory before retrying.

## Three recipes, ready to run

| Recipe | Study | Techniques |
| --- | --- | --- |
| `product` | Sculptural ceramic lamp | Beveled edges, ceramic micro-bump, rough stone, warm/cool studio lighting |
| `abstract` | Interlocking copper orbits | Metallic response, readable silhouette, contact shadows, plinth composition |
| `interior` | Isometric reading nook | Believable scale, furniture, shelves, books, coordinated materials |

Each recipe creates a new scene with an active camera, named objects/materials, an AgX view transform and three area lights. The saved `.blend` holds only that scene: the factory scene with its default Cube, Camera, Light and Material, and every unused datablock, are removed before saving. The CLI starts a fresh Blender process. It refuses to overwrite an existing recipe `.blend`. The recipes are authored procedural baselines, not model-generated results. They are intentionally small and easy to adapt; the material helpers do not simulate physically accurate wood grain or textile fibers.

## Evaluate a model or harness change

1. Select a brief from [briefs.json](briefs.json), and start from the same clean Blender file.
2. Record the exact model ID, harness commit, prompt, tool/vision mode, turn/token limits, Blender version and hardware. Keep the random seed and rendering settings fixed where supported.
3. Run the brief at least three times per configuration. Preserve failures, timeouts and rejected operations in the dataset.
4. Save the `.blend`, final image, viewport evidence and trace. Never score only cherry-picked successes.
5. Run the scene inspector and technical gates. Then review a fixed-size final image using the rubric below, ideally with blinded model labels and two reviewers.
6. Compare technical pass rates, completion rates, latency, token usage and human ratings separately. This repository does not invent a universal quality score.

The six briefs cover product work, interiors, hard-surface detail, stylized scenes, lighting and editing an existing scene. The JSON records acceptance criteria and difficulty, so you can feed the same prompt directly into the harness.

## Technical inspection

`inspect` opens a file in a separate background Blender process and collects scene facts without saving modifications. `score --strict` exits nonzero if any of these gates fail:

- At least one render-visible mesh and an active camera.
- A potential illumination source exists.
- Finite transforms and nonzero scale on render-visible meshes.
- Material assignments, no missing file-backed images and a minimum effective resolution.

These are deliberately limited checks. A camera may point away from the subject. An unconnected emission node may trigger the light heuristic. Linked collections, hidden parents, geometry nodes, UDIMs and procedural assets can require manual inspection. Missing-image checks inspect all loaded file-backed images, including unused assets. Technical passes do **not** prove beautiful composition, watertight geometry, correct exposure or license compliance.

## Human rubric

```sh
blender-quality rubric > ratings.json
# Replace every null with a score from 0 to 5; fill reviewer and evidence.
blender-quality review ratings.json > human-report.json
blender-quality score output/inspection.json > technical-report.json
blender-quality compare technical-report.json human-report.json
```

| Dimension | Look for |
| --- | --- |
| Brief adherence | Subject, style, constraints and requested deliverable |
| Composition | Silhouette, framing, balance and focal hierarchy |
| Geometry | Proportions, intersections and intentional edges |
| Materials | Response, scale, variation and coherence |
| Lighting | Readability, contact, contrast and color |
| Finish | Artifacts, polish and readiness for the intended use |

Anchors: **0** absent/unusable; **1** major failures; **2** substantial fixes needed; **3** acceptable with visible issues; **4** polished with minor issues; **5** excellent for this particular brief. Write evidence-based notes, not just numbers. The normalized human score weights the six dimensions equally; it remains subjective.

## Integration with Astra

Paste a brief into Astra, choose your own provider/API, run Studio quality and download `scene.blend` and its trace. Use the inspector on that scene. The harness manifest reports status, model, turns, reported tokens and elapsed time; retain it alongside this lab's reports. Import the reusable material/light helpers into trusted Blender scripts, or give the model a brief and the rubric as creative constraints.

Recommended starting models and their official sources live in the [harness README](https://github.com/AleBrito124356/astra-blender-harness#recommended-starting-models). There is no published model leaderboard here yet.

## Development

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests
python -m build
```

The CI template in `docs/github-actions.yml` tests report validation and scoring without downloading Blender or spending API credits. Copy it to `.github/workflows/ci.yml` and push with a workflow-enabled credential to activate GitHub Actions. See [validation.md](docs/validation.md) for Blender runtime checks. MIT licensed. Original recipes by Alejandro Brito. Independent of the Blender Foundation.
