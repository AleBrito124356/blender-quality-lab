# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **5/10 passed**, 0 warnings.

## Fix first

1. **Nothing the camera can see renders: the scene has no geometry objects at all** Add geometry the camera can see.
2. **The scene has no active camera** Add a camera and set it as scene.camera.

## Failed gates

- `renderable_geometry`: the scene has no geometry objects at all
- `camera`: scene.camera is not set
- `subject_in_frame`: blocked by camera, renderable_geometry
- `not_cropped_or_tiny`: blocked by camera, renderable_geometry
- `materials`: blocked by renderable_geometry

## What the camera sees

No active camera.

## Grounding

No geometry with surface area to check.

## Lighting

World 'Low contrast studio world': strength 0.25, radiance 0.0347.
