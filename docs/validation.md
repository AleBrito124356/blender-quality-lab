# Validation record

Validated on 2026-09-09 with Windows, Python 3.14 and Blender 4.5.9 LTS.

- 13 automated scoring/provenance tests passed.
- All three recipes (`product`, `abstract`, `interior`) built and saved their .blend files.
- All three rendered successfully with Cycles CPU, 32 samples, denoising and 960 × 720 resolution.
- All three .blend files were reopened in separate background Blender processes and inspected.
- Each recipe passed 8/8 technical gates. This is not an aesthetic score.
- The abstract composition was visually inspected and its lowest ring was grounded on the plinth before the final render.
- Reference images in this directory come from these actual Blender renders.
- Distribution wheels and source archives were built locally. The included CI template tests scoring on Python 3.11/3.13, Windows/Ubuntu. It is not activated in GitHub Actions and does not download or run Blender.

The reference recipes are hand-authored procedural code. No model API was used, and no model ranking is claimed. Blender on macOS/Linux and other Blender versions remain unverified.
