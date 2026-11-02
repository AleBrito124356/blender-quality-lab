"""Run inside Blender: fail in one of the ways a lab script can fail.

Usage: blender ... --python script_failures.py -- raise|exit|sleep
"""

import sys
import time

mode = sys.argv[sys.argv.index("--") + 1]
if mode == "raise":
    raise RuntimeError("boom from the test script")
if mode == "exit":
    raise SystemExit("stopped by the test script")
if mode == "sleep":
    time.sleep(120)
