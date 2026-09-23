# Validation record

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
