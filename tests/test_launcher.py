"""scripts/bpy_launcher.py: the `blender --background ... --python` emulation for a bpy interpreter.

The launcher runs inside a Python that has bpy; here a fake bpy module records what the launcher
does, so the order of the isolation steps is checked without Blender. tests/blender checks the
same guarantees against the real bpy module.
"""

import importlib.util
import os
import subprocess
import sys
import types

import pytest

from blender_quality.runner import LAUNCHER, LAUNCHER_MARKER, LAUNCHER_NO_BPY

spec = importlib.util.spec_from_file_location("bql_bpy_launcher", LAUNCHER)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

ISOLATED = ["--background", "--factory-startup", "--disable-autoexec"]


def test_constants_match_the_runner():
    assert (launcher.NO_BPY, launcher.MARKER) == (LAUNCHER_NO_BPY, LAUNCHER_MARKER)


def test_parse_reads_blenders_command_line():
    options, rest = launcher.parse(
        [*ISOLATED, "scene.blend", "--python-exit-code", "1", "--python", "s.py", "--", "--output", "x"]
    )
    assert options["blend"] == "scene.blend"
    assert (options["script"], options["exit_code"]) == ("s.py", 1)
    assert rest == ["--output", "x"]


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--python", "s.py"], "refusing to run without --background --factory-startup --disable-autoexec"),
        (["--background", "--factory-startup", "--python", "s.py"], "without --disable-autoexec"),
        ([*ISOLATED], "nothing to run"),
        ([*ISOLATED, "--enable-autoexec", "--python", "s.py"], "unsupported option '--enable-autoexec'"),
        ([*ISOLATED, "a.blend", "b.blend", "--python", "s.py"], "unexpected argument 'b.blend'"),
        ([*ISOLATED, "--python-exit-code", "x", "--python", "s.py"], "--python-exit-code needs a number"),
    ],
)
def test_parse_refuses_anything_but_the_isolated_subset(argv, message):
    with pytest.raises(ValueError, match=message):
        launcher.parse(argv)


class FakeBpy(types.ModuleType):
    """Just enough of bpy for the launcher, recording the order of what it is asked to do."""

    def __init__(self, events, factory=True, fail_open=False):
        super().__init__("bpy")
        self.events = events
        self.fail_open = fail_open
        self.app = types.SimpleNamespace(version_string="5.2.3 LTS", factory_startup=factory)
        self.filepaths = types.SimpleNamespace(use_scripts_auto_execute=True)
        self.context = types.SimpleNamespace(preferences=types.SimpleNamespace(filepaths=self.filepaths))
        wm = types.SimpleNamespace(open_mainfile=self.open_mainfile, read_factory_settings=self.factory)
        self.ops = types.SimpleNamespace(wm=wm)

    def factory(self, **kwargs):
        self.events.append(("read_factory_settings", kwargs))

    def open_mainfile(self, **kwargs):
        self.events.append(("open_mainfile", kwargs, self.filepaths.use_scripts_auto_execute))
        if self.fail_open:
            raise RuntimeError("Error: Cannot read file, not a blend file")


@pytest.fixture
def fake_bpy(monkeypatch):
    events = []
    monkeypatch.setattr(launcher, "isolate_user_folders", lambda: events.append(("isolate",)))
    real_import = launcher.import_bpy

    def import_bpy():
        events.append(("import",))
        return real_import()

    monkeypatch.setattr(launcher, "import_bpy", import_bpy)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    module = FakeBpy(events)
    monkeypatch.setitem(sys.modules, "bpy", module)
    return module


def write_script(tmp_path, body):
    script = tmp_path / "script.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_isolates_before_import_and_disables_autoexec_before_loading(fake_bpy, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"BLENDER")
    seen = tmp_path / "argv.txt"
    script = write_script(
        tmp_path,
        "import sys\n"
        f"open({str(seen)!r}, 'w').write(repr(sys.argv[sys.argv.index('--') + 1:]) + ' ' + __name__)\n",
    )
    argv = [*ISOLATED, str(blend), "--python-exit-code", "1", "--python", str(script), "--", "--output", "o"]
    assert launcher.main(argv) == 0
    assert fake_bpy.events[:2] == [("isolate",), ("import",)]
    name, kwargs, autoexec_when_loading = fake_bpy.events[2]
    assert name == "open_mainfile"
    assert kwargs == {"filepath": os.path.abspath(blend), "load_ui": False, "use_scripts": False}
    assert autoexec_when_loading is False
    assert seen.read_text(encoding="utf-8") == "['--output', 'o'] __main__"
    assert sys.argv[1:] == argv  # the whole Blender-style command line, like Blender's sys.argv


def test_factory_settings_are_read_when_bpy_does_not_start_with_them(fake_bpy, tmp_path):
    fake_bpy.app.factory_startup = False
    script = write_script(tmp_path, "")
    assert launcher.main([*ISOLATED, "--python", str(script)]) == 0
    assert ("read_factory_settings", {"use_empty": False}) in fake_bpy.events


def test_script_exception_prints_traceback_and_uses_the_exit_code(fake_bpy, tmp_path, capsys):
    script = write_script(tmp_path, "raise RuntimeError('boom from the script')\n")
    assert launcher.main([*ISOLATED, "--python-exit-code", "1", "--python", str(script)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" in err and "RuntimeError: boom from the script" in err


def test_system_exit_keeps_its_code(fake_bpy, tmp_path):
    script = write_script(tmp_path, "raise SystemExit('Scene not found')\n")
    with pytest.raises(SystemExit) as info:
        launcher.main([*ISOLATED, "--python-exit-code", "1", "--python", str(script)])
    assert info.value.code == "Scene not found"


def test_unreadable_blend_stops_with_an_error(fake_bpy, tmp_path, capsys):
    fake_bpy.fail_open = True
    blend = tmp_path / "broken.blend"
    blend.write_bytes(b"not a blend")
    script = write_script(tmp_path, "raise AssertionError('must not run')\n")
    assert launcher.main([*ISOLATED, str(blend), "--python", str(script)]) == 1
    assert "cannot read" in capsys.readouterr().err
    assert launcher.main([*ISOLATED, str(tmp_path / "missing.blend"), "--python", str(script)]) == 1


def test_stub_bpy_packages_are_not_mistaken_for_blender(fake_bpy, tmp_path, capsys):
    fake_bpy.app = types.SimpleNamespace()  # e.g. fake-bpy-module: type stubs, no running Blender
    assert launcher.main([*ISOLATED, "--python", str(write_script(tmp_path, ""))]) == LAUNCHER_NO_BPY
    assert "not Blender's module" in capsys.readouterr().err


def test_version_prints_like_blender(fake_bpy, capsys):
    assert launcher.main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("Blender 5.2.3 LTS\n")


def test_user_folders_point_to_an_empty_temporary_folder(monkeypatch):
    registered = []
    monkeypatch.setattr(launcher.atexit, "register", lambda *call, **kw: registered.append((call, kw)))
    for variable in launcher.USER_FOLDERS:
        monkeypatch.setenv(variable, "/home/someone/.config/blender")
    launcher.isolate_user_folders()
    root = os.environ["BLENDER_USER_RESOURCES"]
    try:
        assert os.path.isdir(root) and not os.listdir(root)
        for variable in launcher.USER_FOLDERS:
            assert os.environ[variable].startswith(root)
        ((call, kwargs),) = registered
        assert call[1] == root and kwargs == {"ignore_errors": True}
    finally:
        os.rmdir(root)


def test_real_process_refuses_to_run_without_isolation(tmp_path):
    script = write_script(tmp_path, "")
    proc = subprocess.run(
        [sys.executable, "-I", str(LAUNCHER), "--python", str(script)], capture_output=True, text=True
    )
    assert proc.returncode == 2
    assert proc.stderr.startswith(LAUNCHER_MARKER)


@pytest.mark.parametrize(
    "code, status, printed", [(None, 0, ""), (3, 3, ""), ("Scene not found", 1, "Scene not found\n")]
)
def test_system_exit_status_matches_python(code, status, printed, capsys):
    assert launcher.exit_code(SystemExit(code)) == status
    assert capsys.readouterr().err == printed


def test_process_ends_after_running_exit_handlers_and_flushing(tmp_path):
    """finish() runs atexit handlers and flushes before os._exit, so no output or cleanup is lost."""
    marker = tmp_path / "handler.txt"
    code = (
        "import atexit, importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('launcher', {str(LAUNCHER)!r})\n"
        "launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)\n"
        f"atexit.register(lambda: open({str(marker)!r}, 'w').write('ran'))\n"
        "print('buffered output', end='')\n"
        "launcher.finish(7)\n"
    )
    proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert proc.returncode == 7
    assert proc.stdout == "buffered output"
    assert marker.read_text(encoding="utf-8") == "ran"


def test_only_blenders_session_tempdir_is_removed(monkeypatch, tmp_path):
    session = tmp_path / "blender_a1B2c3"
    session.mkdir()
    (session / "quit.blend").write_bytes(b"x")
    module = types.SimpleNamespace(app=types.SimpleNamespace(tempdir=str(session) + os.sep))
    monkeypatch.setitem(sys.modules, "bpy", module)
    launcher.remove_session_tempdir()
    assert not session.exists()
    module.app.tempdir = str(tmp_path) + os.sep  # a user temp folder setting, not the session folder
    launcher.remove_session_tempdir()
    assert tmp_path.exists()
