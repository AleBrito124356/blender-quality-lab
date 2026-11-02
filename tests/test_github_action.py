"""The loop behind action.yml (blender_quality.github_action), with a fake Blender process."""

import shutil
import subprocess
from pathlib import Path

import pytest

from blender_quality import github_action

FIXTURES = Path(__file__).parent / "fixtures" / "inspections"


class FakeBlender:
    """Writes a recorded inspection chosen by the scene's file name; 'crash' scenes fail."""

    def __call__(self, command, **kwargs):
        args = command[command.index("--") + 1 :]
        scene = Path(command[command.index("--python") - 3])
        if "crash" in scene.name:
            return subprocess.CompletedProcess(command, 1, "", "Traceback\nboom\n")
        fixture = "abstract-camera_away.json" if "broken" in scene.name else "abstract.json"
        shutil.copyfile(FIXTURES / fixture, args[args.index("--output") + 1])
        return subprocess.CompletedProcess(command, 0, "", "")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", FakeBlender())
    root = tmp_path / "repo"
    for name in ["scenes/good.blend", "scenes/nested/broken.blend", ".git/ignored.blend", "notes.txt"]:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"BLENDER")
    exe = tmp_path / "blender"
    exe.write_text("fake", encoding="utf-8")
    env = {"GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"), "GITHUB_OUTPUT": str(tmp_path / "output.txt")}
    return root, exe, env, tmp_path


def run(workspace, *extra):
    root, exe, env, tmp_path = workspace
    argv = ["--root", str(root), "--reports", str(tmp_path / "reports"), "--blender", str(exe), *extra]
    code = github_action.main(argv, env=env)
    outputs = dict(
        line.split("=", 1) for line in Path(env["GITHUB_OUTPUT"]).read_text(encoding="utf-8").splitlines()
    )
    summary = Path(env["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
    return code, outputs, summary


def test_matching_files_skips_hidden_folders_and_other_files(workspace):
    root = workspace[0]
    assert github_action.matching_files("**/*.blend", root) == [
        "scenes/good.blend",
        "scenes/nested/broken.blend",
    ]
    assert github_action.matching_files("scenes/*.blend\nother/*.blend", root) == ["scenes/good.blend"]


def test_strict_mode_fails_on_a_failed_gate_and_reports_every_file(workspace, capsys):
    code, outputs, summary = run(workspace, "--strict", "true")
    assert code == 1
    assert (outputs["checked"], outputs["failed"], outputs["errors"]) == ("2", "1", "0")
    assert "| `scenes/nested/broken.blend` | 8/10 | gate failed |" in summary
    assert "| `scenes/good.blend` | 10/10 | all gates pass |" in summary
    assert summary.count("# Scene report: QualityLab_abstract") == 2
    reports = Path(outputs["reports"])
    assert (reports / "scenes" / "good.blend.quality" / "report.md").is_file()
    printed = capsys.readouterr().out
    assert "::error file=scenes/nested/broken.blend,title=blender-quality gate subject_in_frame::" in printed


def test_non_strict_mode_reports_without_failing(workspace, capsys):
    code, outputs, _ = run(workspace, "--strict", "false")
    assert code == 0 and outputs["failed"] == "1"
    assert "::warning file=scenes/nested/broken.blend" in capsys.readouterr().out


def test_a_file_that_cannot_be_checked_fails_even_without_strict(workspace, capsys):
    root = workspace[0]
    (root / "scenes" / "crash.blend").write_bytes(b"BLENDER")
    code, outputs, summary = run(workspace, "--strict", "false", "--files", "scenes/crash.blend")
    assert code == 1 and (outputs["checked"], outputs["errors"]) == ("0", "1")
    assert "Could not be checked: Blender exited with code 1" in summary and "boom" in summary
    assert (
        "::error file=scenes/crash.blend,title=blender-quality%3A could not check::"
        in capsys.readouterr().out
    )


def test_no_matching_file_is_a_warning(workspace, capsys):
    code, outputs, _ = run(workspace, "--files", "nothing/**/*.blend")
    assert code == 0 and outputs["checked"] == "0"
    assert "::warning" in capsys.readouterr().out


def test_subject_collection_is_passed_on(workspace, monkeypatch):
    calls = []
    fake = FakeBlender()
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: calls.append(command) or fake(command, **kw))
    run(workspace, "--files", "scenes/good.blend", "--subject-collection", "ASTRA")
    assert calls[0][calls[0].index("--subject-collection") + 1] == "ASTRA"


def test_report_folders_stay_inside_the_reports_folder(tmp_path):
    assert github_action.report_folder(tmp_path, "a/b.blend") == tmp_path / "a" / "b.blend.quality"
    assert github_action.report_folder(tmp_path, "../up/c.blend") == tmp_path / "_" / "up" / "c.blend.quality"
    absolute = (tmp_path / "x" / "d.blend").as_posix()
    assert github_action.report_folder(tmp_path / "r", absolute).is_relative_to(tmp_path / "r")
