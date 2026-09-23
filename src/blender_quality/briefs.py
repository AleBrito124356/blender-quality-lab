"""The controlled briefs, shipped inside the package so a pip-installed lab can read them."""

import json
import re
from importlib import resources
from pathlib import Path

DIFFICULTIES = {"easy", "medium", "hard"}
KNOWN_DIFFS = {"preserve-and-relight"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def packaged_path():
    return resources.files("blender_quality") / "data" / "briefs.json"


def validate(data):
    """Raise ValueError naming the first problem; return the list of briefs."""
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("briefs file must be an object with schema_version 1")
    briefs = data.get("briefs")
    if not isinstance(briefs, list) or not briefs:
        raise ValueError("briefs file needs a non-empty 'briefs' list")
    seen = set()
    for index, brief in enumerate(briefs):
        where = f"briefs[{index}]"
        if not isinstance(brief, dict):
            raise ValueError(f"{where} is not an object")
        brief_id = brief.get("id")
        if not isinstance(brief_id, str) or not ID_PATTERN.match(brief_id):
            raise ValueError(f"{where} needs a kebab-case 'id'")
        if brief_id in seen:
            raise ValueError(f"duplicate brief id '{brief_id}'")
        seen.add(brief_id)
        if brief.get("difficulty") not in DIFFICULTIES:
            raise ValueError(f"brief '{brief_id}' difficulty must be one of {sorted(DIFFICULTIES)}")
        if not isinstance(brief.get("prompt"), str) or len(brief["prompt"].strip()) < 20:
            raise ValueError(f"brief '{brief_id}' needs a prompt")
        criteria = brief.get("criteria")
        if (
            not isinstance(criteria, list)
            or not criteria
            or not all(isinstance(c, str) and c.strip() for c in criteria)
        ):
            raise ValueError(f"brief '{brief_id}' needs a non-empty list of non-empty criteria")
        for key, kind in (("setup", str), ("subject_collection", str), ("strict_contact", bool)):
            if key in brief and not isinstance(brief[key], kind):
                raise ValueError(f"brief '{brief_id}' field '{key}' must be {kind.__name__}")
        if "diff" in brief and brief["diff"] not in KNOWN_DIFFS:
            raise ValueError(f"brief '{brief_id}' diff must be one of {sorted(KNOWN_DIFFS)}")
    return briefs


def load_briefs(path=None):
    text = Path(path).read_text(encoding="utf-8") if path else packaged_path().read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"briefs file is not valid JSON ({exc.msg} at line {exc.lineno})") from None
    return validate(data)


def get_brief(brief_id, path=None):
    briefs = load_briefs(path)
    for brief in briefs:
        if brief["id"] == brief_id:
            return brief
    raise ValueError(f"unknown brief '{brief_id}'; choose from: {', '.join(b['id'] for b in briefs)}")


def brief_text(brief):
    lines = [f"{brief['id']} ({brief['difficulty']})", "", brief["prompt"], ""]
    if brief.get("setup"):
        lines += [f"Setup: {brief['setup']}", ""]
    lines.append("Acceptance criteria:")
    lines += [f"- {c}" for c in brief["criteria"]]
    checks = []
    if brief.get("subject_collection"):
        checks.append(f"inspect with --subject-collection {brief['subject_collection']}")
    if brief.get("strict_contact"):
        checks.append("score with --strict-contact (floating objects fail)")
    if brief.get("diff"):
        checks.append("compare before/after with `blender-quality diff` (--original INPUT.blend)")
    if checks:
        lines += ["", "Automated checks: " + "; ".join(checks) + "."]
    return "\n".join(lines) + "\n"
