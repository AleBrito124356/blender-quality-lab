# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **10/11 passed**, 3 warnings.

## Fix first

1. **'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' float 3.002 scene units above 'Exhibition plinth' and touch nothing that reaches the ground** Lower 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' by 3.002 so they rest on 'Exhibition plinth'.
   `for name in ['Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3']: bpy.data.objects[name].location.z -= 3.002`
2. **The subject is cut off at the top edge of the frame** Move the camera to (8.721, -12.21, 4.922) (15.16 from the subject centre) and aim it at (0.0, 0.0, 2.761).
   `cam = bpy.data.objects['Editorial camera']; cam.location = (8.721, -12.21, 4.922); cam.rotation_mode = 'XYZ'; cam.rotation_euler = (1.4277, 0.0, 0.6202)`
3. **Key 'Edge separation' and fill 'Large warm key' are nearly equal on the visible subject (1.16:1); fine for catalogue shots, raise the key for more shape** For more shape, double 'Edge separation' or halve 'Large warm key'.
   `bpy.data.objects['Edge separation'].data.energy = 2000`

## Failed gates

- `grounded`: 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' float 3.002 above 'Exhibition plinth'

## What the camera sees

Camera 'Editorial camera' (PERSP, 55.0 mm) at [5.0, -7.0, 4.0], looking along [-0.5555, 0.7777, -0.2944], field of view 36.24 x 27.58 degrees.
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
AAAAAAAAAAAAAAAAAAAAAAAAAABBBBBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBBBBAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Legend: `A` Backdrop floor 88.0%; `B` Exhibition plinth 12.0%

## Subject

'Exhibition plinth', 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' (chosen by heuristic), size [2.4, 1.8, 5.522] around [0.0, 0.0, 2.761].
53.6% of its surface is in frame and it fills 12.0% of the image, centred top-centre at [0.5, 0.82]; 0.0% of the in-frame part is hidden behind other objects.
Cut off at the top edge.
Treated as environment, not subject: 'Backdrop floor'.

## Grounding

- 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' float 3.002 above 'Exhibition plinth'.

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): fill, lights 89.1% of the visible subject, about 2.6474 W/m2.
- 'Cool fill' (AREA, 400.0 W, light blue): accent, lights 100.0% of the visible subject, about 2.024 W/m2.
- 'Edge separation' (AREA, 1000.0 W, light orange): key, lights 67.3% of the visible subject, about 3.0725 W/m2.
Key-to-fill ratio about 1.16:1.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Materials

- 'Brushed copper': mid orange, metallic 0.8, roughness 0.27 (on 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3').
- 'Charcoal stone': near-black, metallic 0.0, roughness 0.65 (on 'Backdrop floor', 'Exhibition plinth').

## Warnings

- (warning) 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3' float 3.002 scene units above 'Exhibition plinth' and touch nothing that reaches the ground.
- (warning) The subject is cut off at the top edge of the frame.
- (info) Key 'Edge separation' and fill 'Large warm key' are nearly equal on the visible subject (1.16:1); fine for catalogue shots, raise the key for more shape.
