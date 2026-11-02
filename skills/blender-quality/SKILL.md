---
name: blender-quality
description: Check a Blender scene an agent built or edited, without vision, and repair it. Use when a .blend (or a scene in a running Blender reached over MCP) must have a camera that frames the subject, geometry that renders, light that reaches the subject, materials, grounded objects and sane animation keys; it returns failed gates, warnings and "Fix first" items with ready-to-run Blender Python. Not an aesthetic judge.
---

# Blender Quality Lab: check, fix, re-check

`blender-quality` inspects a scene from its geometry (no screenshots, no vision model), scores
technical gates and writes a report whose "Fix first" items carry Blender Python. It never runs
Python stored in the .blend.

## Setup (once)

- `pip install git+https://github.com/AleBrito124356/blender-quality-lab` (or `pip install -e .`
  in a clone).
- Blender: an installed Blender 4.5+, or no install at all: `pip install bpy` in a Python 3.13
  environment (bpy 5.x; bpy 4.5 needs Python 3.11) and pass that Python as `--blender`.
- `blender-quality doctor` must name a Blender (`kind: Blender executable` or `bpy module`).

## The loop

1. Save the scene to a `.blend` file.
2. Run `blender-quality check scene.blend --strict --json` (add the subject options below).
   Exit code 0: every gate passed. 1: a gate failed, or Blender failed (an `error:` line on
   stderr and no JSON). 2: bad input. The same report is saved as `scene.quality/report.json`;
   `report.md` is the readable version.
3. Read `fixes` in order (priority 1 is most urgent; 4 and 5 are advisory). Each has
   `problem`, `action` and `python`. Run `python` in the scene's Blender when it fits your intent;
   when `python` is null, do what `action` says. Fix failed gates before exposure warnings: a
   frame that is dark because the camera points away cannot be fixed with exposure.
4. Save and re-check. Stop when the exit code is 0. If the same gate fails twice after its fix,
   stop and report the gate's `detail` instead of looping.
5. Render the final image and run `blender-quality measure render.png` for exposure.

From Python, the same loop is `from blender_quality import api` then `report = api.check(path,
subject_collection="ASTRA")`; `report["all_gates_passed"]`, `report["fixes"]`, `report["markdown"]`.

## Choosing the subject

The gates judge framing and light on the subject. By default it is every visible object except
large flat backdrops (floors, walls) and objects that enclose the camera. Check the report's
Subject section (`subject.objects`, `chosen_by`). If it is wrong:

- `--subject "Lamp*"`: object names or globs, repeatable;
- `--subject-collection ASTRA`: everything in a collection (Astra Blender Harness builds into
  `ASTRA`).

Use the collection when the scene was built into one; use names for a hero object among props.

## A running Blender (MCP `execute_code`)

When the scene lives in a running Blender and is not saved:

1. `code = api.live_inspection_code(subject_collection="ASTRA")` (CLI: `blender-quality live-code`).
2. Send `code` through `execute_code`; it prints one `BQL_INSPECTION_JSON:` line.
3. `inspection = api.parse_live_output(output)`, then `api.describe(inspection)` for the report
   and `api.score(inspection)` for the gates.

The live code opens no file and never saves. It changes viewport visibility and the current
frame while it runs and restores both. It renders no preview, so there are no exposure facts;
use `check` on a saved copy for those. `animation_samples=0` avoids changing the frame at all
(frame-change handlers registered in that Blender would otherwise run).

## What the gates do not tell you

- Passing gates is not a good image: composition, style, proportions and the brief still need
  judgement (the human rubric: `blender-quality rubric`).
- Known false alarms: deliberately floating objects (birds, hanging lamps without a cord) under
  `--strict-contact`; extreme close-ups and very wide shots for `not_cropped_or_tiny`; glass
  counts as an occluder for the camera.
- Known blind spots: volume-, point-cloud- or hair-only subjects are not ray-cast; shadow rays
  ignore small gaps; irradiance is a relative estimate (no bounces); images used only by
  modifiers or drivers are not traced; Python drivers are not evaluated.
- The fix snippets are computed suggestions (camera look-at, light power for the distance, the
  measured floating gap). Re-check after applying them; do not assume they worked.
