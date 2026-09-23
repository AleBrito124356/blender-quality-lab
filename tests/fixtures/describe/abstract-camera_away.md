# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **8/10 passed**, 0 warnings.

## Fix first

1. **only 0.0% of the subject surface is inside the frame (the subject is behind the camera)** Aim the camera at the subject centre (0.0, 0.0, 1.261).
   `cam = bpy.data.objects['Editorial camera']; cam.rotation_mode = 'XYZ'; cam.rotation_euler = (1.2625, 0.0, 0.6202)`

## Failed gates

- `subject_in_frame`: only 0.0% of the subject surface is inside the frame (the subject is behind the camera)
- `not_cropped_or_tiny`: blocked by subject_in_frame

## What the camera sees

Camera 'Editorial camera' (PERSP, 55.0 mm) at [5.0, -7.0, 4.0], looking along [0.5555, -0.7777, -0.2944], field of view 36.24 x 27.58 degrees.
Empty background: 0.0% of the frame.

```text
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Legend: `A` Backdrop floor 100.0%

## Subject

'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3', 'Exhibition plinth' (chosen by heuristic), size [2.4, 1.8, 2.522] around [0.0, 0.0, 1.261].
0.0% of its surface is in frame and it fills 0.0% of the image; 0.0% of the in-frame part is hidden behind other objects.
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
