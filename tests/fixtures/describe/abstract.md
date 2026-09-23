# Scene report: QualityLab_abstract

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **10/10 passed**, 1 warnings.

## Optional improvements

1. **Key 'Cool fill' and fill 'Large warm key' are nearly equal on the visible subject (1.06:1); fine for catalogue shots, raise the key for more shape** For more shape, double 'Cool fill' or halve 'Large warm key'.
   `bpy.data.objects['Cool fill'].data.energy = 800`

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
AAAAAAAAAAAAAAAAAAAAAAAAAAAAADDCCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAEEEECCCCCCDDCCCCCCCAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAEDDECCCCAADDDDAAACCCCAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAEDDCCCEEAAADDDDAAACCCAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAEDDCCEEEAAAADDDDAACCCAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAEDDDCEEEEAAADDDDACCCCAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAEDDDEEEECAADDDCCCCCAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAEEEDEEECCCDDDCCCCAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAABBBBEEEEEEDDDDBBBAAAAAAAAAAAAAAAAAAAAAAAAA
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

Legend: `A` Backdrop floor 79.8%; `B` Exhibition plinth 11.1%; `C` Copper orbit 3 4.1%; `D` Copper orbit 2 2.7%; `E` Copper orbit 1 2.3%

## Subject

'Exhibition plinth', 'Copper orbit 3', 'Copper orbit 2', 'Copper orbit 1' (chosen by heuristic), size [2.4, 1.8, 2.522] around [0.0, 0.0, 1.261].
100.0% of its surface is in frame and it fills 20.2% of the image, centred middle-centre at [0.5, 0.481]; 19.8% of the in-frame part is hidden behind other objects.
Treated as environment, not subject: 'Backdrop floor'.

## Grounding

Every object group rests on or touches something (tolerance 0.005).

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): fill, lights 65.2% of the visible subject, about 2.01 W/m2, partly blocked by 'Copper orbit 3', 'Copper orbit 2' and 1 more.
- 'Cool fill' (AREA, 400.0 W, light blue): key, lights 75.3% of the visible subject, about 2.1329 W/m2, partly blocked by 'Copper orbit 2', 'Copper orbit 1' and 1 more.
- 'Edge separation' (AREA, 1000.0 W, light orange): accent, lights 18.1% of the visible subject, about 0.8639 W/m2, partly blocked by 'Copper orbit 3', 'Copper orbit 1' and 1 more.
Key-to-fill ratio about 1.06:1.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Materials

- 'Brushed copper': mid orange, metallic 0.8, roughness 0.27 (on 'Copper orbit 1', 'Copper orbit 2', 'Copper orbit 3').
- 'Charcoal stone': near-black, metallic 0.0, roughness 0.65 (on 'Backdrop floor', 'Exhibition plinth').

## Warnings

- (info) Key 'Cool fill' and fill 'Large warm key' are nearly equal on the visible subject (1.06:1); fine for catalogue shots, raise the key for more shape.
