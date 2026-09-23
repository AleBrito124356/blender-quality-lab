# Scene report: QualityLab_product

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **11/11 passed**, 1 warnings.

## Optional improvements

1. **Key 'Cool fill' and fill 'Large warm key' are nearly equal on the visible subject (1.17:1); fine for catalogue shots, raise the key for more shape** For more shape, double 'Cool fill' or halve 'Large warm key'.
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
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAACCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAACCCCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAACCCCCCCCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAACCCCCCCCCCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAACCCCCCCCCCCCCCCCCCAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEEEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAABDDDDDDDDBAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAABBBBBBBDDDDDDDDBBBBBBBAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAABBBBBBBBBDDDDDDBBBBBBBBBAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
```

Legend: `A` Backdrop floor 85.2%; `B` Stone plinth 8.0%; `C` Sculptural lamp shade 5.1%; `D` Ceramic lamp foot 1.4%; `E` Ceramic lamp neck 0.3%; `F` Copper shade cap 0.1%

## Subject

'Stone plinth', 'Sculptural lamp shade', 'Ceramic lamp foot', 'Ceramic lamp neck', 'Copper shade cap' (chosen by heuristic), size [2.24, 2.24, 2.105] around [0.0, 0.0, 1.0525].
100.0% of its surface is in frame and it fills 14.8% of the image, centred middle-centre at [0.5, 0.436]; 10.4% of the in-frame part is hidden behind other objects.
- 'Ceramic lamp neck' is 75.8% hidden behind 'Sculptural lamp shade', 'Ceramic lamp foot'.
Treated as environment, not subject: 'Backdrop floor'.

## Grounding

Every object group rests on or touches something (tolerance 0.005).

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): fill, lights 57.0% of the visible subject, about 1.9711 W/m2, partly blocked by 'Sculptural lamp shade', 'Ceramic lamp neck' and 1 more.
- 'Cool fill' (AREA, 400.0 W, light blue): key, lights 79.7% of the visible subject, about 2.2965 W/m2, partly blocked by 'Sculptural lamp shade', 'Ceramic lamp foot' and 1 more.
- 'Edge separation' (AREA, 1000.0 W, light orange): accent, lights 37.1% of the visible subject, about 1.5942 W/m2, partly blocked by 'Sculptural lamp shade', 'Ceramic lamp neck' and 1 more.
Key-to-fill ratio about 1.17:1.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Materials

- 'Brushed copper': mid orange, metallic 0.8, roughness 0.27 (on 'Copper shade cap').
- 'Charcoal stone': near-black, metallic 0.0, roughness 0.65 (on 'Backdrop floor', 'Stone plinth').
- 'Ivory ceramic': light orange, metallic 0.0, roughness 0.24 (on 'Ceramic lamp foot', 'Ceramic lamp neck', 'Sculptural lamp shade').

## Warnings

- (info) Key 'Cool fill' and fill 'Large warm key' are nearly equal on the visible subject (1.17:1); fine for catalogue shots, raise the key for more shape.
