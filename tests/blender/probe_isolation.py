"""Run inside Blender: write the isolation state blender-quality promises, as JSON.

Usage: blender ... --python probe_isolation.py -- OUTPUT.json ARG...
"""

import json
import os
import sys

import bpy

arguments = sys.argv[sys.argv.index("--") + 1 :]
prefs = bpy.context.preferences
with open(arguments[0], "w", encoding="utf-8") as handle:
    json.dump(
        {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
            "factory_startup": bpy.app.factory_startup,
            "autoexec_preference": prefs.filepaths.use_scripts_auto_execute,
            "user_resources": bpy.utils.resource_path("USER"),
            "script_paths": bpy.utils.script_paths(),
            "addons": sorted(addon.module for addon in prefs.addons),
            "argv": sys.argv,
            "arguments": arguments,
            "python_flags": {
                "isolated": sys.flags.isolated,
                "ignore_environment": sys.flags.ignore_environment,
                "no_user_site": sys.flags.no_user_site,
            },
            "blender_variables": sorted(k for k in os.environ if k.startswith("BLENDER_")),
            "file": __file__,
            "name": __name__,
        },
        handle,
    )
