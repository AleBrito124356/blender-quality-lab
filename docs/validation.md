# Validation record

## 2026-11-02: Linux (Ubuntu 24.04, x86-64, no GPU), bpy 5.2.3 LTS on Python 3.13 and bpy 4.5.15 LTS on Python 3.11

No Blender executable was installed; both runtimes are Blender's `bpy` module from PyPI, run through `scripts/bpy_launcher.py`. Mesa provides software EGL.

- 251 offline tests pass (`python -m pytest`), including the API signatures, both JSON Schemas against every recorded inspection and the reports generated from them, the launcher's emulation order with a fake bpy, and the action loop.
- `BLENDER=<bpy 5.2.3 python> python -m pytest -m blender`: 60 passed (72 s). `BLENDER=<bpy 4.5.15 python> python -m pytest -m blender`: 60 passed (61 s; the two suites ran in parallel). The fixtures recorded with Blender 5.2.1 are reproduced on both versions; the recipes pass every gate with `--strict-contact`; each sabotage fails exactly its gate; the `describe` fixes repair all seven broken scenes.
- Isolation, on the bpy kind, each with a control run that shows the planted code fires when isolation is off:
  - a user startup script in `$XDG_CONFIG_HOME/blender/<version>/scripts/startup` does not run. Imported directly, bpy reports that folder as its user resource path; through the launcher it points at an empty temporary folder;
  - a startup script in `BLENDER_SYSTEM_SCRIPTS` does not run, because the variable is removed;
  - `PYTHONPATH` and the user site-packages are ignored (`sys.flags.isolated == 1`);
  - in a `.blend` with a registered text block and a scripted driver that each write a file, neither runs during `check` (preview render included). Opened with autoexec allowed, both do.
- Exceptions in a script and `SystemExit` exit with code 1 and their message in the error tail; `--timeout 5` stops a sleeping script; an unreadable `.blend` is an error, not an empty scene.
- The live inspection code, executed as Blender MCP's `execute_code` does (`exec(code, {"bpy": bpy})`, stdout captured) and with separate globals and locals, gives the same facts as `inspect` on the saved file. Checked on abstract, interior, hidden-collection and animated scenes, and with `--subject`/`--contact-scale`. Afterwards, viewport visibility, the frame and subframe, the datablocks and the namespace are as before. On 4.5, changing viewport state marks the file dirty; on 5.2 it does not. `inspector.unsaved_changes` reports what it was.
- Found and fixed with bpy 4.5.15: after a scripted driver fails to evaluate (it always does under disabled autoexec), the process hangs at exit in a C++ static destructor in `bpy/__init__.so`. `GlobalState::~GlobalState` destroys a condition variable that its "delayed close" thread still waits on. An `inspect` of any file with a Python driver would have run into the 600 s timeout. The launcher now runs the Python exit handlers, removes Blender's session temp folder, flushes, and exits with `os._exit`. bpy 5.2.3 does not hang, and takes the same exit path.
- `check` on the abstract recipe, end to end with a 25% Cycles preview: about 2.1 s on either version (preview render 1.1 s).
- EEVEE renders the `check` preview headless through software EGL with bpy 5.2.3 (7.4 s for a 25% preview with cached shaders).
- A wheel built with `python -m build` was installed with `bpy==5.2.3` into a fresh Python 3.13 venv. Without `--blender` or `BLENDER`, `doctor` found that venv's Python ("current Python interpreter (bpy is importable)"), and `build interior` plus `check --strict --strict-contact` passed 11/11 gates. The wheel ships both schemas and the launcher.
- `.github/workflows/ci.yml` passes actionlint; `action.yml` was parsed and its inputs, outputs and steps checked by hand. The action's loop (`python -m blender_quality.github_action`) was run on two real scenes, one with a Python driver, and wrote the summary, the outputs and both reports. The composite steps themselves (setup-python, venv, pip, apt) have not run on GitHub yet.

Not verified in this round: a Blender executable (none was available), macOS and Windows with bpy, the live inspection inside a GUI Blender (it was run inside background bpy, the way Astra's headless worker runs it), and the GitHub-hosted runners.

## 2026-09-23: Windows 11, Python 3.14.2, Blender 5.2.1 LTS

- 144 offline tests pass (`python -m pytest`): runner and CLI, v1 and v2 gates, PNG decoding, `describe` snapshots, diff, summarize. 46 Blender integration tests pass (`python -m pytest -m blender`, about 3 minutes).
- `blender-quality doctor` finds `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` without `--blender` or PATH. Every call carries `--background --factory-startup --disable-autoexec`, which is checked by tests on the exact command line.
- All three recipes build without DeprecationWarnings. Each saved `.blend` has exactly one scene and no default Cube/Camera/Light/Material (datablock probe in the integration tests).
- Recipes pass 10/10 v2 gates, and 11/11 with `--strict-contact`. The contact analysis found, and the recipes now fix:
  - a 1.5 cm gap under every plinth;
  - interior shelves hovering 5 cm off the wall;
  - an interior edge light blocked by the wall.

  The reference renders were re-rendered after the fix (Cycles CPU, 960 × 720, 32 samples).
- The five scenes that scored 8/8 under schema 1 now fail exactly their target gate:

  | Variant | Fails |
  | --- | --- |
  | camera turned 180° | `subject_in_frame` |
  | meshes in a render-disabled collection | `renderable_geometry` |
  | zero-scale parent | `non_degenerate_world_transform` |
  | no lights, world 0, unused emissive material | `effective_illumination` |
  | sculpture lifted 3 m | `floating` warning, or `grounded` with `--strict-contact` |

  Two animation variants were built through the Blender 5 layered-action API: a valid one passes, and one keyed on frames 300-400 fails `animation_keys_in_range`. A relight-only edit passes the `diff` preserve-and-relight check.
- For all six broken variants, and for a scene whose camera was deleted, the Python fixes printed by `describe` were applied inside Blender. The re-inspected scenes pass every gate, `--strict-contact` included.
- `check` ran without crashing on edge cases that were built in Blender:
  - an empty scene, a scene without a camera, and a panoramic camera (these three are also in the integration suite);
  - an orthographic camera with a text object and a collection instance;
  - a light sealed in an opaque box, which fails `effective_illumination` with "blocked by 'Cube'";
  - a glass occluder with a geometry-nodes instancer;
  - a vertex-only mesh with a missing HDRI, which fails `missing_images` because the image is used.

  The first round of this test found two crashes, both now fixed: a preview render with no camera, and `describe` on a panoramic camera.
- Parity checks inside Blender:
  - camera projection vs `bpy_extras.world_to_camera_view`: max difference 1.2e-6 (perspective and orthographic, lens shift, AUTO/VERTICAL sensor fit);
  - `look_at_euler` vs `to_track_quat('-Z', 'Y')`: 5.6e-7 over 2000 random pairs;
  - the pure-Python PNG statistics vs numpy on the same renders: mean and std equal to four decimals (abstract 0.2971 / 0.1943), percentiles within 0.001.
- Timings:
  - inspection 0.1-0.4 s inside Blender;
  - `check` with a 25% preview about 9 s end to end;
  - `measure` on a 960 × 720 render about 0.8 s.
- The wheel ships `data/briefs.json` and both Blender scripts. It was installed into a fresh virtual environment, where `briefs show`, `describe` and `doctor` worked.

Not verified in this round: Blender 4.x with the rewritten inspector (fallback code paths exist but were not executed), macOS/Linux, EEVEE previews on a GPU-less machine, and scenes over 4 million triangles (ray analysis is then truncated and reported as such).

## 2026-09-09: Windows, Python 3.14, Blender 4.5.9 LTS (schema 1)

- 13 automated scoring/provenance tests passed.
- All three recipes built, rendered (Cycles CPU, 32 samples, denoising, 960 × 720), were reopened in separate background Blender processes and inspected; each passed 8/8 schema 1 gates.
- Distribution wheels and source archives were built locally.

The reference recipes are hand-authored procedural code. No model API was used, and no model ranking is claimed.
