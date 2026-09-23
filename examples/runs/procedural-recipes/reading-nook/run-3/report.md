# Scene report: QualityLab_interior

Blender 5.2.1 LTS, CYCLES 960 x 720. Gates: **11/11 passed**, 2 warnings.

## Optional improvements

1. **Key 'Large warm key' and fill 'Cool fill' are nearly equal on the visible subject (1.07:1); fine for catalogue shots, raise the key for more shape** For more shape, double 'Large warm key' or halve 'Cool fill'.
   `bpy.data.objects['Large warm key'].data.energy = 1800`

## What the camera sees

Camera 'Editorial camera' (PERSP, 55.0 mm) at [5.0, -7.0, 5.0], looking along [-0.5264, 0.7474, -0.4053], field of view 36.24 x 27.58 degrees.
Empty background: 0.0% of the frame.

```text
AAAAAAAAAAACCCCCCCCCCCCCCCBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAAAAAAAAA
AAAAACCCCCCCCCCCCCCCCCCCCCBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAA
AAAAACCCCCCCCCCCCCCCCCCCCCVSSPRRBBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAA
AAAAACCCCCCCCCCCCCCCCCCCCCVSPPRMMBBBBBBBBBBBBBBBBBBBBBBBBBBBAAAA
AAAAACCCCCCCCCCCCCCCCCCCCIIIIIRMMIIBBBBBBBBBBBBBBBBBBBBBBBBBAAAA
AAAAAACCCCCCCCCCCCCCCCCCCCWTTBBBBBIIIBBBBBBBBBBBBBBBBBBBBBBAAAAA
AAAAAACCCCCCCCCCCCCCCCCCCCWTNNXOOBBBBBBBBBBBBBBBBBBBBBBBBBBAAAAA
AAAAAACCCCCCCCCCCCCCCCCCCJJJNNXOOJBBBBBBBBBBBBBBBBBBBBBBBBBAAAAA
AAAAAACCCCCCCCCCCCCCCCCCCCYbbBBcBJJJJBBBBBBBBBHHHHHHBBBBBBBAAAAA
AAAAAACCCCCCCCCCCCCCCCCCCCYEEEEEEEEEBBBBBBBBBBHHHHHHBBBBBBAAAAAA
AAAAAAACCCCCCCCCCCCCCCCCCCaEEEEEEEEEEBBBBBBBBBBHHHHBBBBBBBAAAAAA
AAAAAAACCCCCCCCCCCCCCCCCCCCBEEEEEEEEEBBBBBBBBBBBLBBBBBBBBBAAAAAA
AAAAAAACCCCCCCCCCCCCCCCCDDDDEEEEEEEEEBBBBBBBBBBBLBBBBBBBBBAAAAAA
AAAAAAACCCCCCCCCCCCCDDDDDDFFFFFFEEEEEDDBGGBBBBBBLBBBBBBBBBAAAAAA
AAAAAAAACCCCCCCCDDDDDDFFFFFFFFFFFFFFGGGGGGGGGGBBLBBBBBBBBAAAAAAA
AAAAAAAACCCCCDDDDDDDDDFFFFFFFFFFFFFQDGGGGGGGGGDDDDDDBBBBBAAAAAAA
AAAAAAAADDDDDDDDDDDDDDDZDDDFFFFFDDQQDDDKKKKDDDDDDDDDDDDDDAAAAAAA
AAAAADDDDDDDDDDDDDDDDDDZDDDDDDUDDDDDDDDKKKKDDDDDDDDDDDDAAAAAAAAA
AAAAAAAADDDDDDDDDDDDDDDDDDDDDDUDDDDDDDDDDDDDDDDDDDDDDAAAAAAAAAAA
AAAAAAAAAAAAADDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAADDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAADDDDDDDDDDDDDDDDDDDDDDDDDAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAADDDDDDDDDDDDDDDDDDDAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADDDDDDDDDDDDAAAAAAAAAAAAAAAAAAAAA
```

Legend: `A` Backdrop floor 28.3%; `B` Back wall 22.5%; `D` Walnut platform 18.4%; `C` Side wall 18.4%; `E` Chair back 2.8%; `F` Chair seat 2.4%; `G` Side table top 1.4%; `H` Paper lamp 1.0%; `I` Floating shelf.002 0.6%; `J` Floating shelf.001 0.6%; `K` Side table base 0.5%; `L` Reading lamp stem 0.3%

## Subject

'Chair back', 'Chair seat', 'Side table top', 'Paper lamp', 'Floating shelf.002', 'Floating shelf.001' and 22 more (chosen by heuristic), size [3.37, 2.54, 2.535] around [-0.065, 0.37, 1.3125].
100.0% of its surface is in frame and it fills 12.5% of the image, centred middle-centre at [0.516, 0.553]; 31.9% of the in-frame part is hidden behind other objects.
- 'Book.001' is 74.2% hidden behind 'Chair back', 'Floating shelf', 'Book.002'.
- 'Book.002' is 89.1% hidden behind 'Chair back', 'Book.003'.
- 'Book.003' is 83.6% hidden behind 'Chair back'.
- 'Book.004' is 82.0% hidden behind 'Chair back'.
- 'Book.012' is 51.6% hidden behind 'Book.013'.
- 'Chair leg.001' is 100.0% hidden behind 'Chair seat'.
- 'Floating shelf' is 89.8% hidden behind 'Chair back', 'Book', 'Book.001'.
Treated as environment, not subject: 'Back wall', 'Backdrop floor', 'Side wall', 'Walnut platform'.

## Grounding

Every object group rests on or touches something (tolerance 0.005).

## Lighting

- 'Large warm key' (AREA, 900.0 W, light orange): key, lights 68.5% of the visible subject, about 2.0455 W/m2, partly blocked by 'Side wall', 'Chair seat' and 1 more.
- 'Cool fill' (AREA, 400.0 W, light blue): fill, lights 83.1% of the visible subject, about 1.9174 W/m2, partly blocked by 'Side table top', 'Chair seat' and 1 more.
- 'Edge separation' (AREA, 1000.0 W, light orange): accent, lights 27.9% of the visible subject, about 0.5933 W/m2, partly blocked by 'Floating shelf.002', 'Back wall' and 1 more.
Key-to-fill ratio about 1.07:1.
World 'Low contrast studio world': strength 0.25, radiance 0.0347.

## Materials

- 'Brushed copper': mid orange, metallic 0.8, roughness 0.27 (on 'Book', 'Book.002', 'Book.004' and 7 more).
- 'Ivory ceramic': light orange, metallic 0.0, roughness 0.24 (on 'Back wall', 'Paper lamp', 'Side wall').
- 'Moss textile': mid green, metallic 0.0, roughness 0.9 (on 'Book.001', 'Book.003', 'Book.006' and 5 more).
- 'Warm walnut': mid orange, metallic 0.0, roughness 0.42 (on 'Chair leg', 'Chair leg.001', 'Chair leg.002' and 7 more).

## Warnings

- (info) 'Chair leg.001' is in frame but hidden behind 'Chair seat'.
- (info) Key 'Large warm key' and fill 'Cool fill' are nearly equal on the visible subject (1.07:1); fine for catalogue shots, raise the key for more shape.
