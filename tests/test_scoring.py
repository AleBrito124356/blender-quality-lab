import math

import pytest

from blender_quality.scoring import RUBRIC, human_report, technical_report


def scene():
    return {
        "schema_version": 1,
        "objects": [
            {"type": "MESH", "hide_render": False, "finite": True, "scale": [1, 1, 1], "material_count": 1}
        ],
        "camera": "Camera",
        "illumination": True,
        "missing_images": [],
        "resolution": [960, 720],
    }


def test_valid_scene():
    assert technical_report(scene())["pass_rate"] == 100


def test_empty_scene_is_not_quality():
    data = scene()
    data["objects"] = []
    data["camera"] = None
    report = technical_report(data)
    assert report["passed"] < report["total"]
    assert not next(c for c in report["checks"] if c["id"] == "visible_geometry")["passed"]


def test_zero_scale_and_missing_images_fail():
    data = scene()
    data["objects"][0]["scale"] = [1, 0, 1]
    data["missing_images"] = ["lost.png"]
    assert technical_report(data)["passed"] == 6


def test_human_report_records_provenance():
    data = {"scores": dict.fromkeys(RUBRIC, 4), "reviewer": "reviewer-A", "evidence": "final.png"}
    report = human_report(data)
    assert report["score"] == 80
    assert report["reviewer"] == "reviewer-A"


@pytest.mark.parametrize("score", [True, -1, 6, math.nan, math.inf, "5", None])
def test_invalid_scores_rejected(score):
    data = {"scores": dict.fromkeys(RUBRIC, score), "reviewer": "A", "evidence": "render.png"}
    with pytest.raises(ValueError):
        human_report(data)


def test_all_dimensions_required():
    with pytest.raises(ValueError):
        human_report({"scores": {"brief": 4}, "reviewer": "A", "evidence": "x"})


def test_schema_version_required():
    with pytest.raises(ValueError):
        technical_report({"schema_version": 2})
