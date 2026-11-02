"""Run inside Blender on a recipe .blend: add Python that runs only if autoexec is allowed, save a copy.

- a registered text block (use_module) that writes CANARY_DIR/text-block.txt when the file loads;
- a scripted driver whose expression writes CANARY_DIR/driver.txt when the depsgraph evaluates it.

The isolation tests open this file through blender-quality and require that neither file appears;
a control run with autoexec enabled shows that both canaries do fire.
Usage: blender ... recipe.blend --python make_autoexec_canary.py -- OUTPUT.blend CANARY_DIR
"""

import sys
from pathlib import Path

import bpy

output, canary_dir = sys.argv[sys.argv.index("--") + 1 :][:2]
text_file = (Path(canary_dir) / "text-block.txt").as_posix()
driver_file = (Path(canary_dir) / "driver.txt").as_posix()

text = bpy.data.texts.new("bql_autoexec_canary.py")
text.write(f"open({text_file!r}, 'w').write('registered text block ran')\n")
text.use_module = True

target = bpy.data.objects["Exhibition plinth"]
target["bql_canary"] = 0.0
driver = target.driver_add('["bql_canary"]').driver
driver.type = "SCRIPTED"
driver.expression = f"0.0 * len(__import__('pathlib').Path({driver_file!r}).write_text('driver ran') * 'x')"

bpy.ops.wm.save_as_mainfile(filepath=output, copy=True)
print("CANARY_SCENE=" + output)
