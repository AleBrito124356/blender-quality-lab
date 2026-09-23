# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **6/10 passed**, 1 warnings.

## Fix first

1. **Nothing the camera can see renders: 'Backdrop floor', 'Exhibition plinth', 'Copper orbit 1', 'Copper orbit 2' and 1 more: collection 'Disabled for render' has hide_render on** Make the geometry render again.
   `bpy.data.collections['Disabled for render'].hide_render = False`

## Failed gates

- `renderable_geometry`: 'Backdrop floor', 'Exhibition plinth', 'Copper orbit 1', 'Copper orbit 2' and 1 more: collection 'Disabled for render' has hide_render on
- `subject_in_frame`: blocked by renderable_geometry
- `not_cropped_or_tiny`: blocked by renderable_geometry
- `materials`: blocked by renderable_geometry

## What the camera sees

Camera 'Editorial camera' (PERSP, 55.0 mm) at [5.0, -7.0, 4.0], looking along [-0.5555, 0.7777, -0.2944], field of view 36.24 x 27.58 degrees.

## Grounding

Every object group rests on or touches something (tolerance 0.005).

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): no effect on the visible subject, lights n/a of the visible subject, about 0.0 W/m2.
- 'Cool fill' (AREA, 400.0 W, light blue): no effect on the visible subject, lights n/a of the visible subject, about 0.0 W/m2.
- 'Edge separation' (AREA, 1000.0 W, light orange): no effect on the visible subject, lights n/a of the visible subject, about 0.0 W/m2.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Warnings

- (info) 5 geometry objects do not render: 'Backdrop floor', 'Exhibition plinth', 'Copper orbit 1', 'Copper orbit 2' and 1 more.
