"""Run inside Blender on a saved .blend: write which datablocks the file carries, as JSON."""

import json
import sys

import bpy

output = sys.argv[sys.argv.index("--") + 1]
with open(output, "w", encoding="utf-8") as handle:
    json.dump(
        {
            "scenes": [s.name for s in bpy.data.scenes],
            "objects": sorted(o.name for o in bpy.data.objects),
            "materials": sorted(m.name for m in bpy.data.materials),
            "cameras": sorted(c.name for c in bpy.data.cameras),
            "lights": sorted(light.name for light in bpy.data.lights),
            "worlds": sorted(w.name for w in bpy.data.worlds),
        },
        handle,
    )
