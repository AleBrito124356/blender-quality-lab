import subprocess
import sys
from pathlib import Path

import pytest

from blender_quality import runner
from blender_quality.runner import (
    BlenderError,
    BlenderNotFound,
    build_command,
    find_blender,
    install_candidates,
    isolated_env,
    output_tail,
    version_key,
)


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
        find_blender(env={"ProgramFiles": str(tmp_path)}, which=no_path, platform="win32")
    message = str(info.value)
    for hint in ["--blender", "BLENDER", "PATH"]:
        assert hint in message


def test_version_key_reads_folder_names():
    assert version_key("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe") == (5, 2)
    assert version_key("/opt/blender-4.5.3-linux-x64/blender") == (4, 5, 3)
    assert version_key("/usr/bin/blender") == ()


def test_isolated_env_removes_script_overrides():
    env = isolated_env({"BLENDER_USER_SCRIPTS": "x", "BLENDER_SYSTEM_SCRIPTS": "y", "PATH": "p"})
    assert env == {"PATH": "p"}


def test_output_tail_prefers_stderr():
    assert output_tail("a\nb\n", "Traceback\nboom\n") == ["Traceback", "boom"]
    assert output_tail(b"only stdout\n", "") == ["only stdout"]
    assert output_tail("\n".join(str(i) for i in range(40)), None)[-1] == "39"


def test_real_process_failure_becomes_blender_error(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("", encoding="utf-8")
    # Python rejects Blender's flags and exits 2: a real non-Blender executable failing.
    with pytest.raises(BlenderError) as info:
        runner.run_blender(sys.executable, script, timeout=60)
    assert info.value.returncode == 2
    assert info.value.output_tail


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
