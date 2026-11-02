"""Run a Blender script through the `bpy` Python module, the way a Blender executable would run it.

blender-quality uses this launcher when the "Blender" it found is a Python interpreter that can
import bpy (`pip install bpy`) instead of a Blender executable. It accepts the same strict subset
of Blender's command line that blender-quality always passes to a Blender executable:

    python -I bpy_launcher.py --background --factory-startup --disable-autoexec [FILE.blend]
        [--python-exit-code N] --python SCRIPT.py [-- ARGS...]
    python -I bpy_launcher.py --version

and keeps the same guarantees:

- Factory settings. Before bpy is imported, Blender's user resource, config, scripts, extensions
  and datafiles folders are pointed at a new empty temporary folder, so no startup file,
  preferences, user scripts or add-ons exist to be loaded, whatever the bpy version defaults to.
- Autoexec is disabled before the file is loaded: `use_scripts_auto_execute = False`, then
  `open_mainfile(load_ui=False, use_scripts=False)`. Registered text blocks and Python drivers in
  the .blend never run. A file that cannot be read stops the run with a non-zero exit code, as
  Blender does in background mode.
- `sys.argv` holds the Blender-style command line, so scripts parse their own arguments after `--`.
- An exception in the script prints its traceback and exits with the --python-exit-code value;
  `SystemExit` behaves as in Blender (its code becomes the exit code).
- The process ends without running bpy's native shutdown: bpy 4.5 can hang forever in a C++ static
  destructor (`GlobalState::~GlobalState` in bpy/__init__.so) after a scripted driver failed to
  evaluate, which every inspection of a file with a Python driver triggers; a Blender executable
  never reaches that code. Instead, Python exit handlers run (this launcher's cleanup), Blender's
  session temp folder (bpy.app.tempdir) is removed as Blender's own exit would remove it, Python
  and C output is flushed, and the process ends with os._exit.

`python -I` keeps the interpreter isolated the way Blender keeps its embedded Python: PYTHONPATH,
the other PYTHON* variables and the user site-packages are ignored, and this folder is not put on
sys.path. The caller also removes BLENDER_USER_*/BLENDER_SYSTEM_* overrides from the environment.

This file must stay standalone: it is run by path and may not import blender_quality.
"""

import atexit
import ctypes
import gc
import os
import runpy
import shutil
import sys
import tempfile
import traceback

REQUIRED = ("--background", "--factory-startup", "--disable-autoexec")
USER_FOLDERS = {
    "BLENDER_USER_RESOURCES": "",
    "BLENDER_USER_CONFIG": "config",
    "BLENDER_USER_SCRIPTS": "scripts",
    "BLENDER_USER_EXTENSIONS": "extensions",
    "BLENDER_USER_DATAFILES": "datafiles",
}
# Exit codes and marker the caller (blender_quality.runner) recognises.
USAGE_ERROR = 2
NO_BPY = 3
MARKER = "BQL_LAUNCHER_ERROR:"


def fail(message, code):
    print(f"{MARKER} {message}", file=sys.stderr, flush=True)
    return code


def parse(argv):
    """(options, script args) from a Blender-style command line; raises ValueError on anything else."""
    options = {"flags": set(), "blend": None, "exit_code": 0, "script": None, "version": False}
    rest = []
    if "--" in argv:
        split = argv.index("--")
        argv, rest = argv[:split], argv[split + 1 :]
    items = iter(argv)
    for item in items:
        if item in REQUIRED:
            options["flags"].add(item)
        elif item in {"--version", "-v"}:
            options["version"] = True
        elif item == "--python-exit-code":
            value = next(items, None)
            if value is None or not value.isdigit() or int(value) > 255:
                raise ValueError("--python-exit-code needs a number from 0 to 255")
            options["exit_code"] = int(value)
        elif item in {"--python", "-P"}:
            if options["script"] is not None:
                raise ValueError("only one --python script is supported")
            options["script"] = next(items, None)
            if options["script"] is None:
                raise ValueError("--python needs a script path")
        elif item.startswith("-"):
            raise ValueError(f"unsupported option {item!r}")
        elif options["blend"] is None and options["script"] is None:
            options["blend"] = item
        else:
            raise ValueError(f"unexpected argument {item!r}")
    if options["version"]:
        return options, rest
    missing = [flag for flag in REQUIRED if flag not in options["flags"]]
    if missing:
        raise ValueError("refusing to run without " + " ".join(missing) + " (isolation is not optional)")
    if options["script"] is None:
        raise ValueError("nothing to run: pass --python SCRIPT.py")
    return options, rest


def isolate_user_folders():
    """Point every Blender user folder at a new empty temporary folder, removed at exit."""
    root = tempfile.mkdtemp(prefix="bql-bpy-")
    # Registered before bpy is imported, so it runs after bpy's own exit handlers (atexit is LIFO).
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    for variable, folder in USER_FOLDERS.items():
        os.environ[variable] = os.path.join(root, folder) if folder else root


def import_bpy():
    """The real bpy module, or (None, reason)."""
    try:
        import bpy
    except Exception as exc:  # ImportError, or a broken native module
        return None, f"{type(exc).__name__}: {exc}"
    version = getattr(getattr(bpy, "app", None), "version_string", None)
    if not isinstance(version, str):
        return None, "the installed 'bpy' is not Blender's module (a stub package such as fake-bpy-module?)"
    return bpy, None


def main(argv):
    try:
        options, script_args = parse(argv)
    except ValueError as exc:
        return fail(str(exc), USAGE_ERROR)
    isolate_user_folders()
    bpy, problem = import_bpy()
    if bpy is None:
        return fail(f"{sys.executable} cannot import bpy ({problem})", NO_BPY)
    if options["version"]:
        print(f"Blender {bpy.app.version_string}")
        print(f"\tbpy module: Python {sys.version.split()[0]} at {sys.executable}")
        return 0
    if not bpy.app.factory_startup:
        bpy.ops.wm.read_factory_settings(use_empty=False)
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    blend = options["blend"]
    if blend is not None:
        if not os.path.isfile(blend):
            return fail(f"cannot read {blend}: no such file", 1)
        try:
            bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend), load_ui=False, use_scripts=False)
        except RuntimeError as exc:
            return fail(f"cannot read {blend}: {str(exc).strip()}", 1)
    script = os.path.abspath(options["script"])
    sys.argv = [sys.executable, *argv]  # what Blender puts in sys.argv: its whole command line
    sys.stdout.flush()
    try:
        namespace = runpy.run_path(script, run_name="__main__")
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        return options["exit_code"]
    namespace.clear()  # close what the script left open (files flush) before the process ends
    return 0


def exit_code(exc):
    """The exit status Python itself would give an uncaught SystemExit (printing its message)."""
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code & 0xFF
    print(exc.code, file=sys.stderr)
    return 1


def flush_c_stdio():
    """Flush Blender's C-level stdout/stderr buffers, which os._exit would drop."""
    try:
        libc = ctypes.CDLL("ucrtbase") if os.name == "nt" else ctypes.CDLL(None)
        libc.fflush(None)
    except (AttributeError, OSError, TypeError):
        pass


def remove_session_tempdir():
    """Delete Blender's per-process temp folder (<temp>/blender_XXXXXX/), which bpy's exit would."""
    bpy = sys.modules.get("bpy")
    tempdir = getattr(getattr(bpy, "app", None), "tempdir", "") if bpy is not None else ""
    if isinstance(tempdir, str) and os.path.basename(os.path.normpath(tempdir)).startswith("blender_"):
        shutil.rmtree(tempdir, ignore_errors=True)


def finish(code):
    """End the process without bpy's native shutdown (see the module docstring)."""
    gc.collect()
    run_exit_handlers = getattr(atexit, "_run_exitfuncs", None)
    if run_exit_handlers is not None:
        try:
            run_exit_handlers()
        except BaseException:
            traceback.print_exc()
    remove_session_tempdir()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError, ValueError):
            pass
    flush_c_stdio()
    os._exit(code)


if __name__ == "__main__":
    try:
        status = main(sys.argv[1:])
    except SystemExit as stop:
        status = exit_code(stop)
    finish(status)
