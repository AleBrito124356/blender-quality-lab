"""Packaged briefs, scene diff and run aggregation."""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from blender_quality import cli
from blender_quality.briefs import get_brief, load_briefs, packaged_path, validate
from blender_quality.diff import diff_inspections
from blender_quality.scoring import RUBRIC
from blender_quality.summarize import summarize

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "inspections"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def run_cli(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


# ---------------------------------------------------------------- briefs


def test_packaged_briefs_are_valid():
    briefs = load_briefs()
    assert packaged_path().is_file()
    assert len(briefs) == 6
    assert len({b["id"] for b in briefs}) == 6
    assert all(b["criteria"] and all(c.strip() for c in b["criteria"]) for b in briefs)
    assert get_brief("preserve-and-relight")["diff"] == "preserve-and-relight"
    assert get_brief("reading-nook")["strict_contact"] is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["briefs"].append(copy.deepcopy(d["briefs"][0])), "duplicate brief id"),
        (lambda d: d["briefs"][0].update(difficulty="brutal"), "difficulty"),
        (lambda d: d["briefs"][0].update(criteria=[]), "criteria"),
        (lambda d: d["briefs"][0].update(criteria=["ok", " "]), "criteria"),
        (lambda d: d["briefs"][0].update(id="Bad Id"), "kebab-case"),
        (lambda d: d.update(schema_version=2), "schema_version 1"),
    ],
)
def test_brief_validation_names_the_problem(mutate, message):
    data = json.loads(packaged_path().read_text(encoding="utf-8"))
    mutate(data)
    with pytest.raises(ValueError, match=message):
        validate(data)


def test_briefs_cli(capsys, tmp_path):
    code, out, _ = run_cli(capsys, "briefs", "list")
    assert code == 0 and out.splitlines()[0].startswith("ceramic-lamp")
    code, out, _ = run_cli(capsys, "briefs", "show", "copper-orbits", "--prompt-only")
    assert out.strip() == get_brief("copper-orbits")["prompt"]
    code, out, _ = run_cli(capsys, "briefs", "show", "reading-nook")
    assert "Acceptance criteria:" in out and "--strict-contact" in out and "--subject-collection ASTRA" in out
    code, _, err = run_cli(capsys, "briefs", "show", "nope")
    assert code == 2 and "unknown brief 'nope'" in err
    broken = tmp_path / "briefs.json"
    broken.write_text(json.dumps({"schema_version": 1, "briefs": [{"id": "x"}]}), encoding="utf-8")
    code, _, err = run_cli(capsys, "briefs", "validate", "--file", broken)
    assert code == 2 and "difficulty" in err


# ---------------------------------------------------------------- diff


def test_identical_scenes_have_no_changes():
    result = diff_inspections(load("abstract"), load("abstract"))
    assert result["summary"] == ["No changes"]
    verdict = result["preserve_and_relight"]
    assert verdict["geometry_preserved"] and not verdict["lighting_changed"]
    assert verdict["passed"] is False  # nothing was relit


def test_relight_made_in_blender_preserves_geometry():
    result = diff_inspections(load("abstract"), load("abstract-relight"))
    verdict = result["preserve_and_relight"]
    assert verdict == {
        "geometry_preserved": True,
        "names_preserved": True,
        "materials_preserved": True,
        "lighting_changed": True,
        "camera_changed": True,
        "input_unchanged": None,
        "passed": True,
    }
    changed = {item["name"]: item["changes"] for item in result["lights"]["changed"]}
    assert changed["Large warm key"][0] == "energy 900.0 -> 1100.0"
    assert result["objects"]["changed"] == []


def test_moved_geometry_is_caught():
    result = diff_inspections(load("abstract"), load("abstract-floating"))
    moved = {item["name"]: item["changes"] for item in result["objects"]["changed"]}
    assert set(moved) == {"Copper orbit 1", "Copper orbit 2", "Copper orbit 3"}
    assert moved["Copper orbit 1"] == ["moved by (0, 0, 3)"]
    assert result["preserve_and_relight"]["geometry_preserved"] is False


def test_zero_scale_parent_is_caught():
    result = diff_inspections(load("abstract"), load("abstract-zero_scale_parent"))
    assert result["objects"]["added"] == ["Collapsed parent"]
    plinth = next(i for i in result["objects"]["changed"] if i["name"] == "Exhibition plinth")
    assert "parent None -> 'Collapsed parent'" in plinth["changes"]
    assert "world scale (1, 1, 1) -> (0, 0, 0)" in plinth["changes"]


def test_renames_and_material_edits_are_caught():
    after = load("abstract")
    ring = next(o for o in after["objects"] if o["name"] == "Copper orbit 1")
    ring["name"] = "Ring A"
    after["materials"][0]["roughness"] = 0.9
    result = diff_inspections(load("abstract"), after)
    assert result["objects"]["renamed"] == [["Copper orbit 1", "Ring A"]]
    assert result["materials"]["changed"] == ["Brushed copper"]
    verdict = result["preserve_and_relight"]
    assert not verdict["names_preserved"] and not verdict["materials_preserved"]


def test_original_file_hash_proves_no_overwrite(tmp_path):
    before = load("abstract")
    original = tmp_path / "input.blend"
    original.write_bytes(b"pretend blend")
    assert (
        diff_inspections(before, load("abstract-relight"), original)["preserve_and_relight"][
            "input_unchanged"
        ]
        is False
    )
    before["file"]["sha256"] = hashlib.sha256(b"pretend blend").hexdigest()
    result = diff_inspections(before, load("abstract-relight"), original)
    assert result["preserve_and_relight"]["input_unchanged"] is True
    assert result["preserve_and_relight"]["passed"] is True


def test_diff_cli(capsys):
    code, out, _ = run_cli(
        capsys,
        "diff",
        FIXTURES / "abstract.json",
        FIXTURES / "abstract-relight.json",
        "--format",
        "md",
        "--strict",
    )
    assert code == 0 and "**PASS**" in out
    code, _, _ = run_cli(
        capsys, "diff", FIXTURES / "abstract.json", FIXTURES / "abstract-floating.json", "--strict"
    )
    assert code == 1


# ---------------------------------------------------------------- summarize


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def technical(passed, total=10):
    return {"schema_version": 2, "kind": "technical", "passed": passed, "total": total, "checks": []}


@pytest.fixture
def run_tree(tmp_path):
    brief = tmp_path / "runs" / "model-a" / "copper-orbits"
    write(
        brief / "r1" / "manifest.json",
        {"status": "completed", "elapsed_seconds": 100, "total_tokens": 1000, "steps": 10},
    )
    write(brief / "r1" / "technical.json", technical(10))
    write(
        brief / "r1" / "human-a.json",
        {"reviewer": "A", "evidence": "r1.png", "scores": dict.fromkeys(RUBRIC, 4)},
    )
    scores_b = {**dict.fromkeys(RUBRIC, 4), "brief": 2, "composition": 5}
    write(
        brief / "r1" / "human-b.json",
        {
            "schema_version": 1,
            "kind": "human",
            "reviewer": "B",
            "evidence": "r1.png",
            "scores": scores_b,
            "score": 76.7,
        },
    )
    write(brief / "r2" / "manifest.json", {"status": "failed", "elapsed_seconds": 50, "total_tokens": 400})
    write(brief / "r3" / "manifest.json", {"status": "timeout", "elapsed_seconds": 600})
    write(brief / "r3" / "technical.json", technical(8))
    # No manifest: the inspection is scored here, with --strict-contact because the brief asks for it.
    (brief / "r4").mkdir()
    shutil.copyfile(FIXTURES / "abstract-floating.json", brief / "r4" / "inspection.json")
    return tmp_path / "runs"


def test_summary_counts_failures_timeouts_and_disagreement(run_tree):
    summary = summarize(run_tree)
    (row,) = summary["rows"]
    assert row["runs"] == 4
    assert row["statuses"] == {"completed": 2, "failed": 1, "timeout": 1}
    assert row["completion_rate"] == 0.5  # r1 + r4
    assert row["all_gates_pass_rate"] == 0.25  # only r1; r2 has no report, r4 floats under --strict-contact
    assert row["mean_gate_share"] == pytest.approx((1 + 0.8 + 10 / 11) / 3, abs=1e-3)
    human = row["human"]
    assert human["reviews"] == 2 and human["mean"] == pytest.approx(78.35)
    assert human["stdev"] == pytest.approx(2.33)
    assert human["max_reviewer_gap"]["brief"] == 2 and human["max_reviewer_gap"]["composition"] == 1
    assert row["median_elapsed_s"] == 100 and row["median_tokens"] == 700 and row["median_turns"] == 10
    assert "no combined ranking" in summary["note"]


def test_summary_of_the_real_example_runs(capsys):
    summary = summarize(ROOT / "examples" / "runs")
    rows = {(r["config"], r["brief"]): r for r in summary["rows"]}
    assert len(rows) == 4
    for brief in ["ceramic-lamp", "copper-orbits", "reading-nook"]:
        row = rows[("procedural-recipes", brief)]
        assert (row["runs"], row["completion_rate"], row["all_gates_pass_rate"]) == (3, 1.0, 1.0)
    sabotaged = rows[("sabotaged-recipes", "copper-orbits")]
    assert sabotaged["statuses"] == {"completed": 3, "timeout": 1}
    assert sabotaged["all_gates_pass_rate"] == 0.0
    code, out, _ = run_cli(capsys, "summarize", ROOT / "examples" / "runs")
    assert code == 0 and "| sabotaged-recipes | copper-orbits | 4 | 75% | 0% |" in out


def test_compare_is_a_deprecated_alias(capsys, run_tree):
    code, out, err = run_cli(capsys, "compare", run_tree)
    assert code == 0 and "deprecated" in err and json.loads(out)["kind"] == "run_summary"
    report = run_tree / "model-a" / "copper-orbits" / "r1" / "technical.json"
    code, out, err = run_cli(capsys, "compare", report)
    assert code == 0 and json.loads(out)["reports"][0]["passed"] == 10


def test_empty_runs_directory_is_explained(capsys, tmp_path):
    code, _, err = run_cli(capsys, "summarize", tmp_path)
    assert code == 2 and "no runs found" in err
