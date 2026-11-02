import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from blender_quality import runner
from blender_quality.runner import (
    KIND_BLENDER,
    KIND_BPY,
    LAUNCHER,
    BlenderError,
    BlenderLocation,
    BlenderNotFound,
    build_command,
    find_blender,
    install_candidates,
    isolated_env,
    kind_of,
    output_tail,
    version_key,
)

HAS_BPY = importlib.util.find_spec("bpy") is not None


def make_exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake", encoding="utf-8")
    return path


def no_path(_name):
    return None


def only_blender_on_path(name):
    return "/usr/bin/blender" if name == "blender" else None


def test_command_always_carries_isolation_flags():
    command = build_command("blender", "script.py", ["--output", "x.json"], blend_file="scene.blend")
    assert command[:4] == ["blender", "--background", "--factory-startup", "--disable-autoexec"]
    # The .blend is loaded after the safety flags and before the script runs.
    assert command.index("scene.blend") < command.index("--python")
    assert command[command.index("--python-exit-code") + 1] == "1"
    assert command[command.index("--") + 1 :] == ["--output", "x.json"]


def test_explicit_blender_wins_over_everything(tmp_path):
    explicit = make_exe(tmp_path / "custom" / "blender.exe")
    env = {"BLENDER": str(make_exe(tmp_path / "env" / "blender.exe"))}
    found = find_blender(str(explicit), env=env, which=lambda _: "/usr/bin/blender")
    assert found.path == str(explicit)
    assert found.source == "--blender"


def test_explicit_install_folder_is_accepted(tmp_path):
    exe = make_exe(tmp_path / "Blender 5.2" / "blender.exe")
    assert find_blender(str(exe.parent), env={}, which=no_path).path == str(exe)


def test_missing_explicit_blender_does_not_fall_back(tmp_path):
    with pytest.raises(BlenderNotFound, match="--blender"):
        find_blender(str(tmp_path / "nope.exe"), env={}, which=only_blender_on_path)


def test_environment_variable_before_path(tmp_path):
    exe = make_exe(tmp_path / "env" / "blender.exe")
    found = find_blender(env={"BLENDER": str(exe)}, which=lambda _: "/usr/bin/blender")
    assert (found.path, found.source) == (str(exe), "BLENDER environment variable")


def test_broken_environment_variable_is_an_error(tmp_path):
    with pytest.raises(BlenderNotFound, match="BLENDER="):
        find_blender(env={"BLENDER": str(tmp_path / "missing")}, which=no_path)


def test_path_before_install_folders(tmp_path):
    make_exe(tmp_path / "Blender Foundation" / "Blender 5.2" / "blender.exe")
    found = find_blender(
        env={"ProgramFiles": str(tmp_path)}, which=lambda _: "/usr/bin/blender", platform="win32"
    )
    assert (found.path, found.source) == ("/usr/bin/blender", "PATH")


def test_windows_install_folders_prefer_highest_version(tmp_path):
    for version in ["4.5", "5.2", "5.10", "3.6"]:
        make_exe(tmp_path / "Blender Foundation" / f"Blender {version}" / "blender.exe")
    found = find_blender(env={"ProgramFiles": str(tmp_path)}, which=no_path, platform="win32")
    assert found.source == "standard install folder"
    assert Path(found.path).parent.name == "Blender 5.10"
    listed = install_candidates("win32", {"ProgramFiles": str(tmp_path)})
    assert [p.parent.name for p in listed] == ["Blender 5.10", "Blender 5.2", "Blender 4.5", "Blender 3.6"]


def test_macos_and_linux_install_folders(tmp_path):
    root, home = tmp_path / "root", tmp_path / "home"
    make_exe(root / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender")
    assert len(install_candidates("darwin", {}, home, root)) == 1
    make_exe(root / "opt" / "blender-4.5.3-linux-x64" / "blender")
    newest = make_exe(root / "opt" / "blender-5.2.1-linux-x64" / "blender")
    make_exe(root / "snap" / "bin" / "blender")
    linux = install_candidates("linux", {}, home, root)
    assert linux[0] == newest
    assert len(linux) == 3


def test_nothing_found_explains_every_option(tmp_path):
    with pytest.raises(BlenderNotFound) as info:
        find_blender(env={"ProgramFiles": str(tmp_path)}, which=no_path, platform="win32", current=None)
    message = str(info.value)
    for hint in ["--blender", "BLENDER", "PATH", "pip install bpy"]:
        assert hint in message


def test_version_key_reads_folder_names():
    assert version_key("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe") == (5, 2)
    assert version_key("/opt/blender-4.5.3-linux-x64/blender") == (4, 5, 3)
    assert version_key("/usr/bin/blender") == ()


def test_isolated_env_removes_script_overrides():
    env = isolated_env({"BLENDER_USER_SCRIPTS": "x", "BLENDER_SYSTEM_SCRIPTS": "y", "PATH": "p"})
    assert env == {"PATH": "p"}


def test_isolated_env_removes_resource_and_python_overrides():
    # BLENDER_SYSTEM_RESOURCES / BLENDER_USER_RESOURCES (Blender 4.2+) relocate the folders startup
    # scripts are loaded from, and BLENDER_SYSTEM_PYTHON swaps the bundled Python library.
    overrides = [
        "BLENDER_SYSTEM_RESOURCES",
        "BLENDER_USER_RESOURCES",
        "BLENDER_SYSTEM_PYTHON",
        "BLENDER_SYSTEM_DATAFILES",
        "BLENDER_USER_DATAFILES",
    ]
    env = isolated_env({**dict.fromkeys(overrides, "/elsewhere"), "HOME": "h"})
    assert env == {"HOME": "h"}


def test_output_tail_prefers_stderr():
    assert output_tail("a\nb\n", "Traceback\nboom\n") == ["Traceback", "boom"]
    assert output_tail(b"only stdout\n", "") == ["only stdout"]
    assert output_tail("\n".join(str(i) for i in range(40)), None)[-1] == "39"


def test_real_process_failure_becomes_blender_error(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("", encoding="utf-8")
    # Run as if it were a Blender executable, Python rejects Blender's flags and exits 2.
    with pytest.raises(BlenderError) as info:
        runner.run_blender(BlenderLocation(sys.executable, "test", KIND_BLENDER), script, timeout=60)
    assert info.value.returncode == 2
    assert info.value.output_tail


@pytest.mark.skipif(HAS_BPY, reason="this Python can import bpy")
def test_python_without_bpy_is_reported_as_not_found(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("", encoding="utf-8")
    with pytest.raises(BlenderNotFound, match="cannot import bpy") as info:
        runner.run_blender(sys.executable, script, timeout=60)
    assert "pip install bpy" in str(info.value)
    with pytest.raises(BlenderNotFound, match="cannot import bpy"):
        runner.blender_version(BlenderLocation(sys.executable, "test", KIND_BPY))


def test_bpy_command_runs_the_launcher_with_blenders_own_arguments():
    blender = build_command("blender", "s.py", ["--output", "x.json"], blend_file="scene.blend")
    python = build_command("python3", "s.py", ["--output", "x.json"], blend_file="scene.blend", kind=KIND_BPY)
    # `python -I` ignores PYTHONPATH and the user site-packages, as Blender's own Python does.
    assert python[:3] == ["python3", "-I", str(LAUNCHER)]
    assert python[3:] == blender[1:]


@pytest.mark.parametrize(
    "name, kind",
    [
        ("python", KIND_BPY),
        ("python3", KIND_BPY),
        ("python3.13", KIND_BPY),
        ("python.exe", KIND_BPY),
        ("pythonw.exe", KIND_BPY),
        ("pypy3", KIND_BPY),
        ("blender", KIND_BLENDER),
        ("blender.exe", KIND_BLENDER),
        ("Blender", KIND_BLENDER),
        ("blender-launcher.exe", KIND_BLENDER),
    ],
)
def test_kind_from_unambiguous_names(name, kind):
    def probe(_path):
        raise AssertionError("an unambiguous name must not start the program")

    assert kind_of(Path("/somewhere") / name, probe) == kind


@pytest.mark.parametrize(
    "stdout, kind", [("Blender 5.2.1 LTS\n\tbuild date: x\n", KIND_BLENDER), ("Python 3.13.1\n", KIND_BPY)]
)
def test_ambiguous_names_are_probed_with_version(monkeypatch, stdout, kind):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert kind_of("/opt/tools/b3d") == kind
    ((command, kwargs),) = calls
    assert command == ["/opt/tools/b3d", "--version"]
    assert "BLENDER_SYSTEM_SCRIPTS" not in kwargs["env"]


def test_probe_rejects_other_programs(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda command, **_: subprocess.CompletedProcess(command, 0, "GNU bash 5\n", "")
    )
    with pytest.raises(BlenderNotFound, match="neither a Blender executable nor a Python"):
        kind_of("/bin/sh-like")


def test_explicit_python_is_a_bpy_interpreter(tmp_path):
    python = make_exe(tmp_path / "venv" / "bin" / "python3.13")
    found = find_blender(str(python), env={}, which=no_path)
    assert (found.path, found.source, found.kind) == (str(python), "--blender", KIND_BPY)
    found = find_blender(env={"BLENDER": str(python)}, which=only_blender_on_path)
    assert (found.kind, found.source) == (KIND_BPY, "BLENDER environment variable")


def test_python_names_on_path_are_resolved(tmp_path):
    python = make_exe(tmp_path / "python3.13")
    found = find_blender(
        "python3.13", env={}, which=lambda name: str(python) if name == "python3.13" else None
    )
    assert (found.path, found.kind) == (str(python), KIND_BPY)


def test_bpy_interpreters_come_after_every_blender_executable(tmp_path):
    python = make_exe(tmp_path / "bpy" / "python")
    current = BlenderLocation("/venv/bin/python", "current Python interpreter (bpy is importable)", KIND_BPY)
    env = {"BLENDER_PYTHON": str(python)}
    on_path = find_blender(env=env, which=only_blender_on_path, current=current)
    assert (on_path.source, on_path.kind) == ("PATH", KIND_BLENDER)
    installed = make_exe(tmp_path / "root" / "opt" / "blender-5.2.1-linux-x64" / "blender")
    folder = find_blender(env=env, which=no_path, platform="linux", root=tmp_path / "root", home=tmp_path)
    assert folder.path == str(installed)
    found = find_blender(env=env, which=no_path, platform="linux", root=tmp_path / "x", home=tmp_path / "x")
    assert (found.path, found.source, found.kind) == (
        str(python),
        "BLENDER_PYTHON environment variable",
        KIND_BPY,
    )
    last = find_blender(
        env={}, which=no_path, platform="linux", root=tmp_path / "x", home=tmp_path / "x", current=current
    )
    assert last == current


def test_broken_blender_python_variable_is_an_error(tmp_path):
    with pytest.raises(BlenderNotFound, match="BLENDER_PYTHON="):
        find_blender(
            env={"BLENDER_PYTHON": str(tmp_path / "missing")},
            which=no_path,
            platform="linux",
            root=tmp_path,
            home=tmp_path,
        )


def test_current_interpreter_needs_bpy(monkeypatch):
    monkeypatch.delitem(sys.modules, "bpy", raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert runner.current_interpreter() is None
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "bpy" else None)
    found = runner.current_interpreter()
    assert (found.path, found.kind) == (sys.executable, KIND_BPY)


def test_inside_a_running_blender_its_executable_is_used(monkeypatch):
    class App:
        binary_path = "/opt/blender-5.2/blender"

    class FakeBpy:
        app = App

    monkeypatch.setitem(sys.modules, "bpy", FakeBpy)
    found = runner.current_interpreter()
    assert (found.path, found.kind) == ("/opt/blender-5.2/blender", KIND_BLENDER)


def test_bpy_failures_are_labelled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 1, "", "Traceback\nboom\n"),
    )
    with pytest.raises(
        BlenderError, match=r"^Blender \(bpy module\) exited with code 1 while running s\.py$"
    ):
        runner.run_blender(BlenderLocation("python3", "test", KIND_BPY), tmp_path / "s.py")


def test_timeout_becomes_blender_error(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command, kwargs["timeout"], output=b"Fra:1", stderr=b"still rendering"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BlenderError, match="did not finish within 5 s") as info:
        runner.run_blender("blender", tmp_path / "s.py", timeout=5)
    assert info.value.output_tail == ["still rendering"]


def test_unstartable_executable_becomes_blender_error(tmp_path):
    with pytest.raises(BlenderError, match="Could not start Blender"):
        runner.run_blender(str(tmp_path / "missing.exe"), tmp_path / "s.py")
