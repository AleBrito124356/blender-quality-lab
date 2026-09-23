"""Find Blender and run it as an isolated, non-interactive process.

Every command that starts Blender goes through :func:`run_blender`, so the safety
flags cannot be forgotten by one code path: ``--background`` (no UI),
``--factory-startup`` (no user preferences, add-ons or startup file) and
``--disable-autoexec`` (Python embedded in the .blend, such as registered text
blocks and scripted drivers, never runs). Environment overrides that would add
user or site script folders are removed as well. The lab inspects untrusted,
AI-generated scenes, so isolation is the default and not an option.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "BLENDER"
ISOLATION_FLAGS = ("--background", "--factory-startup", "--disable-autoexec")
DEFAULT_TIMEOUT = 600
TAIL_LINES = 12
# Variables that make Blender load extra user/site script folders (and their startup scripts).
SCRUBBED_ENV = (
    "BLENDER_USER_SCRIPTS",
    "BLENDER_USER_CONFIG",
    "BLENDER_USER_EXTENSIONS",
    "BLENDER_SYSTEM_SCRIPTS",
    "BLENDER_SYSTEM_EXTENSIONS",
)


class BlenderError(RuntimeError):
    """Blender could not be started, failed, or did not finish in time."""

    def __init__(self, message, *, returncode=None, output_tail=()):
        super().__init__(message)
        self.returncode = returncode
        self.output_tail = list(output_tail)


class BlenderNotFound(BlenderError):
    """No usable Blender executable was found."""


@dataclass(frozen=True)
class BlenderLocation:
    path: str
    source: str


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


def find_blender(explicit=None, *, env=None, which=None, platform=None, home=None, root=None):
    """Locate Blender: --blender, then $BLENDER, then PATH, then standard install folders."""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    if explicit:
        resolved = _resolve(explicit, which)
        if not resolved:
            raise BlenderNotFound(f"--blender {explicit!r} is not an existing Blender executable")
        return BlenderLocation(resolved, "--blender")
    if env.get(ENV_VAR):
        resolved = _resolve(env[ENV_VAR], which)
        if not resolved:
            raise BlenderNotFound(f"{ENV_VAR}={env[ENV_VAR]!r} is not an existing Blender executable")
        return BlenderLocation(resolved, f"{ENV_VAR} environment variable")
    on_path = which("blender")
    if on_path:
        return BlenderLocation(on_path, "PATH")
    candidates = install_candidates(platform, env, home, root)
    if candidates:
        return BlenderLocation(str(candidates[0]), "standard install folder")
    raise BlenderNotFound(
        "Blender was not found. Pass --blender PATH, set the BLENDER environment variable, "
        "add blender to PATH or install it in the standard location for this OS."
    )


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


def build_command(blender, script, script_args=(), blend_file=None):
    command = [str(blender), *ISOLATION_FLAGS]
    if blend_file is not None:
        command.append(str(blend_file))
    command += ["--python-exit-code", "1", "--python", str(script), "--", *map(str, script_args)]
    return command


def run_blender(blender, script, script_args=(), *, blend_file=None, timeout=DEFAULT_TIMEOUT, verbose=False):
    """Run a Python script inside an isolated background Blender and return its captured output."""
    command = build_command(blender, script, script_args, blend_file)
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
            f"Blender did not finish within {timeout:g} s; it was stopped (raise --timeout for heavy scenes)",
            output_tail=output_tail(exc.stdout, exc.stderr),
        ) from None
    except OSError as exc:
        raise BlenderError(f"Could not start Blender at {blender}: {exc.strerror or exc}") from None
    elapsed = time.perf_counter() - started
    if verbose:
        sys.stderr.write(_text(proc.stdout))
        sys.stderr.write(_text(proc.stderr))
    if proc.returncode != 0:
        raise BlenderError(
            f"Blender exited with code {proc.returncode} while running {Path(script).name}",
            returncode=proc.returncode,
            output_tail=output_tail(proc.stdout, proc.stderr),
        )
    return BlenderRun(command, _text(proc.stdout), _text(proc.stderr), elapsed)


def blender_version(blender, timeout=60):
    """The first line of `blender --version`, e.g. 'Blender 5.2.1 LTS'."""
    try:
        proc = subprocess.run(
            [str(blender), "--background", "--factory-startup", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=isolated_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise BlenderError(f"{blender} --version did not answer within {timeout} s") from None
    except OSError as exc:
        raise BlenderError(f"Could not start Blender at {blender}: {exc.strerror or exc}") from None
    for line in _text(proc.stdout).splitlines():
        if re.match(r"\s*Blender \d", line):
            return line.strip()
    raise BlenderError(
        f"{blender} did not report a Blender version (exit code {proc.returncode})",
        returncode=proc.returncode,
        output_tail=output_tail(proc.stdout, proc.stderr),
    )
