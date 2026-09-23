# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **7/10 passed**, 0 warnings.

## Fix first

1. **The scene has no active camera** Add a 50 mm camera at (5.088, -7.123, 5.331) framing the subject.
   `cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera')); bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam; cam.location = (5.088, -7.123, 5.331); cam.rotation_euler = (1.1355, 0.0, 0.6202)`

## Failed gates

- `camera`: scene.camera is not set
- `subject_in_frame`: blocked by camera
- `not_cropped_or_tiny`: blocked by camera

## What the camera sees

No active camera.

## Subject

'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3', 'Exhibition plinth' (chosen by heuristic), size [2.4, 1.8, 2.522] around [0.0, 0.0, 1.261].
Treated as environment, not subject: 'Backdrop floor'.

## Grounding

Every object group rests on or touches something (tolerance 0.005).

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): fill, lights 34.9% of the visible subject, about 0.9848 W/m2, partly blocked by 'Copper orbit 3', 'Copper orbit 1' and 1 more.
- 'Cool fill' (AREA, 400.0 W, light blue): accent, lights 29.6% of the visible subject, about 0.7706 W/m2, partly blocked by 'Copper orbit 2', 'Copper orbit 3' and 1 more.
- 'Edge separation' (AREA, 1000.0 W, light orange): key, lights 31.1% of the visible subject, about 1.429 W/m2, partly blocked by 'Copper orbit 2', 'Copper orbit 3' and 1 more.
Key-to-fill ratio about 1.45:1.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Materials

- 'Brushed copper': mid orange, metallic 0.8, roughness 0.27 (on 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3').
- 'Charcoal stone': near-black, metallic 0.0, roughness 0.65 (on 'Backdrop floor', 'Exhibition plinth').
