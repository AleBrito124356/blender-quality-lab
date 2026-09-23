import json
import subprocess
import sys

import pytest

from blender_quality import cli
from blender_quality.scoring import RUBRIC


class FakeBlender:
    """Records subprocess.run calls and writes the output a real script would write."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.calls = []
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.returncode == 0 and "--" in command:
            script_args = command[command.index("--") + 1 :]
            if "--output" in script_args and "inspect_scene.py" in command[command.index("--python") + 1]:
                with open(script_args[script_args.index("--output") + 1], "w", encoding="utf-8") as handle:
                    handle.write("{}")
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def fake_exe(tmp_path):
    exe = tmp_path / "blender.exe"
    exe.write_text("fake", encoding="utf-8")
    return exe


def run_cli(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("command", ["build", "inspect"])
def test_blender_commands_are_isolated(command, monkeypatch, capsys, tmp_path, fake_exe):
    fake = FakeBlender()
    monkeypatch.setattr(subprocess, "run", fake)
    if command == "build":
        argv = ["build", "abstract", "--output", tmp_path / "out", "--blender", fake_exe]
    else:
        scene = tmp_path / "scene.blend"
        scene.write_bytes(b"BLENDER")
        argv = ["inspect", scene, "--output", tmp_path / "inspection.json", "--blender", fake_exe]
    code, _out, _err = run_cli(capsys, *argv)
    assert code == 0
    ((called, kwargs),) = fake.calls
    assert "--factory-startup" in called and "--disable-autoexec" in called and "--background" in called
    assert called.index("--disable-autoexec") < called.index("--python")
    assert kwargs["timeout"] == 600
    assert "BLENDER_USER_SCRIPTS" not in kwargs["env"]


def test_timeout_option_is_passed(monkeypatch, capsys, tmp_path, fake_exe):
    fake = FakeBlender()
    monkeypatch.setattr(subprocess, "run", fake)
    run_cli(capsys, "build", "product", "--output", tmp_path / "o", "--blender", fake_exe, "--timeout", "42")
    assert fake.calls[0][1]["timeout"] == 42


def test_build_uses_blender_environment_variable(monkeypatch, capsys, tmp_path, fake_exe):
    fake = FakeBlender()
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setenv("BLENDER", str(fake_exe))
    code, out, _ = run_cli(capsys, "build", "interior", "--output", tmp_path / "o")
    assert code == 0
    assert fake.calls[0][0][0] == str(fake_exe)
    assert "interior.blend" in out


def test_refuses_to_overwrite_recipe(capsys, tmp_path, fake_exe):
    (tmp_path / "abstract.blend").write_bytes(b"x")
    code, _, err = run_cli(capsys, "build", "abstract", "--output", tmp_path, "--blender", fake_exe)
    assert code == 2
    assert "Refusing to overwrite" in err


def assert_clean_error(err, code, expected_code, fragment):
    assert code == expected_code
    assert "Traceback" not in err
    assert err.startswith("blender-quality: error: ")
    assert fragment in err.splitlines()[0]


def test_blender_failure_is_one_line_plus_tail(monkeypatch, capsys, tmp_path, fake_exe):
    monkeypatch.setattr(
        subprocess, "run", FakeBlender(1, stderr="Traceback (most recent call last):\nboom\n")
    )
    code, _, err = run_cli(capsys, "build", "abstract", "--output", tmp_path / "o", "--blender", fake_exe)
    assert code == 1
    assert (
        err.splitlines()[0]
        == "blender-quality: error: Blender exited with code 1 while running build_scene.py"
    )
    assert "  | boom" in err.splitlines()


def test_real_non_blender_executable_fails_cleanly(capsys, tmp_path):
    code, _, err = run_cli(
        capsys, "build", "abstract", "--output", tmp_path / "o", "--blender", sys.executable
    )
    assert_clean_error(err, code, 1, "Blender exited with code 2")


def test_timeout_is_reported_cleanly(monkeypatch, capsys, tmp_path, fake_exe):
    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    code, _, err = run_cli(capsys, "build", "abstract", "--output", tmp_path / "o", "--blender", fake_exe)
    assert_clean_error(err, code, 1, "did not finish within 600 s")


def test_missing_blender_is_reported_cleanly(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("BLENDER", raising=False)
    monkeypatch.setattr(
        cli, "find_blender", lambda explicit: (_ for _ in ()).throw(cli.BlenderError("not here"))
    )
    code, _, err = run_cli(capsys, "build", "abstract", "--output", tmp_path / "o")
    assert_clean_error(err, code, 1, "not here")


def test_unfilled_rubric_is_rejected_cleanly(capsys, tmp_path):
    code, template, _ = run_cli(capsys, "rubric")
    assert code == 0
    path = tmp_path / "ratings.json"
    path.write_text(template, encoding="utf-8")
    code, _, err = run_cli(capsys, "review", path)
    assert_clean_error(err, code, 2, "has no score yet")


def test_placeholder_reviewer_is_rejected(capsys, tmp_path):
    ratings = {"reviewer": "YOUR_NAME", "evidence": "render.png", "scores": dict.fromkeys(RUBRIC, 5)}
    path = tmp_path / "ratings.json"
    path.write_text(json.dumps(ratings), encoding="utf-8")
    code, _, err = run_cli(capsys, "review", path)
    assert_clean_error(err, code, 2, "placeholder reviewer")


def test_empty_evidence_is_rejected(capsys, tmp_path):
    ratings = {"reviewer": "reviewer-A", "evidence": " ", "scores": dict.fromkeys(RUBRIC, 5)}
    path = tmp_path / "ratings.json"
    path.write_text(json.dumps(ratings), encoding="utf-8")
    code, _, err = run_cli(capsys, "review", path)
    assert_clean_error(err, code, 2, "evidence")


def test_partial_inspection_is_rejected_cleanly(capsys, tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"schema_version": 1, "objects": []}), encoding="utf-8")
    code, _, err = run_cli(capsys, "score", path)
    assert_clean_error(err, code, 2, "missing the required field 'camera'")


def test_invalid_json_is_rejected_cleanly(capsys, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    code, _, err = run_cli(capsys, "score", path)
    assert_clean_error(err, code, 2, "not valid JSON")


def test_missing_file_is_rejected_cleanly(capsys, tmp_path):
    code, _, err = run_cli(capsys, "score", tmp_path / "nope.json")
    assert_clean_error(err, code, 2, "file not found")


def test_doctor_reports_version(monkeypatch, capsys, fake_exe):
    fake = FakeBlender(stdout="Blender 5.2.1 LTS\n\tbuild date: 2026-08-25\n")
    monkeypatch.setattr(subprocess, "run", fake)
    code, out, _ = run_cli(capsys, "doctor", "--blender", fake_exe, "--json")
    report = json.loads(out)
    assert code == 0
    assert report["version"] == "Blender 5.2.1 LTS"
    assert report["found_via"] == "--blender"
    assert "--factory-startup" in fake.calls[0][0]


def test_doctor_without_blender_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_blender", lambda explicit: (_ for _ in ()).throw(cli.BlenderError("none")))
    code, out, _ = run_cli(capsys, "doctor")
    assert code == 1
    assert "not found" in out
