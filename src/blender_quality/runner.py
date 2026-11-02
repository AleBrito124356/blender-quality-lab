"""Find Blender and run it as an isolated, non-interactive process.

"Blender" is one of two kinds:

- ``blender``: a Blender executable;
- ``bpy``: a Python interpreter that can import the ``bpy`` module (``pip install bpy``). It runs
  ``scripts/bpy_launcher.py`` with ``python -I``, which emulates the Blender command line below.

Every command that starts Blender goes through :func:`run_blender`, so the safety
flags cannot be forgotten by one code path: ``--background`` (no UI),
``--factory-startup`` (no user preferences, add-ons or startup file) and
``--disable-autoexec`` (Python embedded in the .blend, such as registered text
blocks and scripted drivers, never runs). Environment overrides that would add
user or site script folders are removed as well. The lab inspects untrusted,
AI-generated scenes, so isolation is the default and not an option.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "BLENDER"
PYTHON_ENV_VAR = "BLENDER_PYTHON"
KIND_BLENDER = "blender"  # a Blender executable
KIND_BPY = "bpy"  # a Python interpreter that can import bpy
KIND_LABELS = {KIND_BLENDER: "Blender executable", KIND_BPY: "bpy module in a Python interpreter"}
ISOLATION_FLAGS = ("--background", "--factory-startup", "--disable-autoexec")
LAUNCHER = Path(__file__).parent / "scripts" / "bpy_launcher.py"
# Kept in step with scripts/bpy_launcher.py, which must not import this package.
LAUNCHER_NO_BPY = 3
LAUNCHER_MARKER = "BQL_LAUNCHER_ERROR:"
DEFAULT_TIMEOUT = 600
PROBE_TIMEOUT = 60
TAIL_LINES = 12
# Variables that make Blender load extra user/site script folders (and their startup scripts), or
# replace its resource or bundled-Python folders. Blender itself ignores PYTHONPATH and friends
# unless --python-use-system-env is given; the bpy launcher gets the same through `python -I`.
SCRUBBED_ENV = (
    "BLENDER_USER_RESOURCES",
    "BLENDER_USER_SCRIPTS",
    "BLENDER_USER_CONFIG",
    "BLENDER_USER_EXTENSIONS",
    "BLENDER_USER_DATAFILES",
    "BLENDER_SYSTEM_RESOURCES",
    "BLENDER_SYSTEM_SCRIPTS",
    "BLENDER_SYSTEM_EXTENSIONS",
    "BLENDER_SYSTEM_DATAFILES",
    "BLENDER_SYSTEM_PYTHON",
)
PYTHON_NAME = re.compile(r"^(python|pypy)(\d+(\.\d+)*)?w?$")
_DETECT = object()


class BlenderError(RuntimeError):
    """Blender could not be started, failed, or did not finish in time."""

    def __init__(self, message, *, returncode=None, output_tail=()):
        super().__init__(message)
        self.returncode = returncode
        self.output_tail = list(output_tail)


class BlenderNotFound(BlenderError):
    """No usable Blender executable (or Python interpreter that can import bpy) was found."""


@dataclass(frozen=True)
class BlenderLocation:
    path: str
    source: str
    kind: str = KIND_BLENDER

    @property
    def label(self):
        """How errors name it: 'Blender' or 'Blender (bpy module)'."""
        return "Blender (bpy module)" if self.kind == KIND_BPY else "Blender"

    @property
    def display(self):
        return f"{self.path} [bpy module]" if self.kind == KIND_BPY else self.path


@dataclass(frozen=True)
class BlenderRun:
    command: list
    stdout: str
    stderr: str
    elapsed: float


def version_key(path):
    """Sort key from the version in an install folder name ('Blender 5.2', 'blender-4.5.3-linux-x64')."""
    for part in reversed(Path(path).parts[:-1]):
        match = re.search(r"(\d+(?:\.\d+)+)", part)
        if match:
            return tuple(int(n) for n in match.group(1).split("."))
    return ()


def install_candidates(platform=None, env=None, home=None, root=None):
    """Existing Blender executables in the standard install folders, highest version first."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    root = Path("/") if root is None else Path(root)
    found = []
    if platform.startswith("win"):
        bases = []
        for key in ("ProgramFiles", "ProgramW6432"):
            if env.get(key) and env[key] not in bases:
                bases.append(env[key])
        if not bases:
            bases = ["C:/Program Files"]
        for base in bases:
            found += Path(base, "Blender Foundation").glob("Blender*/blender.exe")
            found.append(Path(base, "Steam", "steamapps", "common", "Blender", "blender.exe"))
    elif platform == "darwin":
        for base in (root / "Applications", home / "Applications"):
            found += base.glob("Blender*.app/Contents/MacOS/Blender")
    else:
        found += [root / "usr" / "bin" / "blender", root / "usr" / "local" / "bin" / "blender"]
        found += [root / "snap" / "bin" / "blender", home / ".local" / "bin" / "blender"]
        found += (root / "opt").glob("blender*/blender")
        found += home.glob("blender*/blender")
    unique = []
    for path in found:
        if path.is_file() and path not in unique:
            unique.append(path)
    # Stable sort: equal versions keep the search order above.
    return sorted(unique, key=version_key, reverse=True)


def _resolve(value, which):
    path = Path(value).expanduser()
    if path.is_file():
        return str(path)
    if path.is_dir():
        for name in ("blender.exe", "blender", "Contents/MacOS/Blender"):
            if (path / name).is_file():
                return str(path / name)
    return which(value)


def _probe_kind(path):
    """Ask the program itself: both Blender and Python answer --version and exit at once."""
    try:
        proc = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT,
            env=isolated_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise BlenderError(f"{path} --version did not answer within {PROBE_TIMEOUT} s") from None
    except OSError as exc:
        raise BlenderError(f"Could not start Blender at {path}: {exc.strerror or exc}") from None
    for line in (_text(proc.stdout) + "\n" + _text(proc.stderr)).splitlines():
        if re.match(r"\s*Blender \d", line):
            return KIND_BLENDER
        if re.match(r"\s*Python \d", line):
            return KIND_BPY
    raise BlenderNotFound(
        f"{path} is neither a Blender executable nor a Python interpreter "
        f"(`{Path(path).name} --version` did not print 'Blender X' or 'Python X')"
    )


def kind_of(path, probe=None):
    """'blender' for a Blender executable, 'bpy' for a Python interpreter (to import bpy with).

    The file name decides when it is unambiguous (blender, blender.exe, Blender; python, python3.13,
    python.exe, pythonw.exe); anything else is run once with --version to see what answers.
    """
    name = Path(path).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if PYTHON_NAME.match(name):
        return KIND_BPY
    if name.startswith("blender"):
        return KIND_BLENDER
    return (probe or _probe_kind)(path)


def current_interpreter():
    """The running Blender (when called from inside it) or this Python, if it can import bpy."""
    bpy = sys.modules.get("bpy")
    binary = getattr(getattr(bpy, "app", None), "binary_path", "") if bpy is not None else ""
    if binary:
        return BlenderLocation(binary, "the running Blender", KIND_BLENDER)
    try:
        importable = importlib.util.find_spec("bpy") is not None
    except (ImportError, ValueError):
        importable = False
    if importable and sys.executable:
        return BlenderLocation(sys.executable, "current Python interpreter (bpy is importable)", KIND_BPY)
    return None


def find_blender(
    explicit=None, *, env=None, which=None, platform=None, home=None, root=None, current=_DETECT, probe=None
):
    """Locate Blender: --blender, $BLENDER, PATH, standard install folders, then a bpy interpreter.

    --blender and $BLENDER accept a Blender executable, its install folder, or a Python interpreter
    that can import bpy. When no Blender executable is found, $BLENDER_PYTHON is used, and then the
    current interpreter if it can import bpy (pass current=None to skip that last step).
    """
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    for value, source, label in (
        (explicit, "--blender", f"--blender {explicit!r}"),
        (env.get(ENV_VAR), f"{ENV_VAR} environment variable", f"{ENV_VAR}={env.get(ENV_VAR)!r}"),
    ):
        if value:
            resolved = _resolve(value, which)
            if not resolved:
                raise BlenderNotFound(f"{label} is not an existing Blender executable or Python interpreter")
            return BlenderLocation(resolved, source, kind_of(resolved, probe))
    on_path = which("blender")
    if on_path:
        return BlenderLocation(on_path, "PATH")
    candidates = install_candidates(platform, env, home, root)
    if candidates:
        return BlenderLocation(str(candidates[0]), "standard install folder")
    if env.get(PYTHON_ENV_VAR):
        resolved = _resolve(env[PYTHON_ENV_VAR], which)
        if not resolved:
            raise BlenderNotFound(
                f"{PYTHON_ENV_VAR}={env[PYTHON_ENV_VAR]!r} is not an existing Python interpreter"
            )
        return BlenderLocation(resolved, f"{PYTHON_ENV_VAR} environment variable", kind_of(resolved, probe))
    found = current_interpreter() if current is _DETECT else current
    if found is not None:
        return found
    raise BlenderNotFound(
        "Blender was not found. Pass --blender PATH, set the BLENDER environment variable, "
        "add blender to PATH or install it in the standard location for this OS; "
        "or `pip install bpy` (Python 3.13 for bpy 5.x) and pass that Python as --blender."
    )


def as_location(blender):
    """A BlenderLocation from a location or a bare path (whose kind is then detected)."""
    if isinstance(blender, BlenderLocation):
        return blender
    return BlenderLocation(str(blender), "caller", kind_of(blender))


def isolated_env(env=None):
    env = dict(os.environ if env is None else env)
    for key in SCRUBBED_ENV:
        env.pop(key, None)
    return env


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def output_tail(stdout, stderr, lines=TAIL_LINES):
    """The last meaningful lines, preferring stderr (where Blender prints Python tracebacks)."""
    for stream in (_text(stderr), _text(stdout)):
        kept = [line.rstrip() for line in stream.splitlines() if line.strip()]
        if kept:
            return kept[-lines:]
    return []


def build_command(blender, script, script_args=(), blend_file=None, kind=KIND_BLENDER):
    """The command line; a bpy interpreter runs the launcher with Blender's own arguments."""
    arguments = [*ISOLATION_FLAGS]
    if blend_file is not None:
        arguments.append(str(blend_file))
    arguments += ["--python-exit-code", "1", "--python", str(script), "--", *map(str, script_args)]
    if kind == KIND_BPY:
        return [str(blender), "-I", str(LAUNCHER), *arguments]
    return [str(blender), *arguments]


def _launcher_error(location, proc):
    """A BlenderNotFound for a Python interpreter that cannot import bpy, else None."""
    if location.kind != KIND_BPY or proc.returncode != LAUNCHER_NO_BPY:
        return None
    for line in _text(proc.stderr).splitlines():
        if line.startswith(LAUNCHER_MARKER):
            return BlenderNotFound(
                line[len(LAUNCHER_MARKER) :].strip()
                + ". Install Blender's bpy module into it (`pip install bpy`: bpy 5.x needs Python 3.13, "
                "4.5 needs Python 3.11) or pass a Blender executable.",
                returncode=proc.returncode,
            )
    return None


def run_blender(blender, script, script_args=(), *, blend_file=None, timeout=DEFAULT_TIMEOUT, verbose=False):
    """Run a Python script inside an isolated background Blender and return its captured output.

    `blender` is a BlenderLocation (from find_blender) or a path, whose kind is then detected.
    """
    location = as_location(blender)
    command = build_command(location.path, script, script_args, blend_file, location.kind)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=isolated_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise BlenderError(
            f"{location.label} did not finish within {timeout:g} s; it was stopped "
            "(raise --timeout for heavy scenes)",
            output_tail=output_tail(exc.stdout, exc.stderr),
        ) from None
    except OSError as exc:
        raise BlenderError(f"Could not start Blender at {location.path}: {exc.strerror or exc}") from None
    elapsed = time.perf_counter() - started
    if verbose:
        sys.stderr.write(_text(proc.stdout))
        sys.stderr.write(_text(proc.stderr))
    if proc.returncode != 0:
        raise _launcher_error(location, proc) or BlenderError(
            f"{location.label} exited with code {proc.returncode} while running {Path(script).name}",
            returncode=proc.returncode,
            output_tail=output_tail(proc.stdout, proc.stderr),
        )
    return BlenderRun(command, _text(proc.stdout), _text(proc.stderr), elapsed)


def blender_version(blender, timeout=PROBE_TIMEOUT):
    """The first line of `blender --version`, e.g. 'Blender 5.2.1 LTS' (the same for a bpy interpreter)."""
    location = as_location(blender)
    if location.kind == KIND_BPY:
        command = [location.path, "-I", str(LAUNCHER), "--version"]
    else:
        command = [location.path, "--background", "--factory-startup", "--version"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=isolated_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise BlenderError(f"{location.path} --version did not answer within {timeout} s") from None
    except OSError as exc:
        raise BlenderError(f"Could not start Blender at {location.path}: {exc.strerror or exc}") from None
    problem = _launcher_error(location, proc)
    if problem is not None:
        raise problem
    for line in _text(proc.stdout).splitlines():
        if re.match(r"\s*Blender \d", line):
            return line.strip()
    raise BlenderError(
        f"{location.path} did not report a Blender version (exit code {proc.returncode})",
        returncode=proc.returncode,
        output_tail=output_tail(proc.stdout, proc.stderr),
    )
