"""Aggregate evaluation runs without inventing a combined score.

Layout: RUNS_DIR/<config>/<brief>/<run>/ with any of
- manifest.json: status, model, turns/steps, tokens/total_tokens, elapsed/elapsed_seconds
  (the Astra Blender Harness manifest keys are read as-is);
- technical.json: a `blender-quality score` report, or inspection.json, which is scored here
  (with --strict-contact when the brief asks for it);
- human*.json: filled rubrics or `blender-quality review` reports, one per reviewer.

Failures and timeouts count: a run without a technical report fails the gates, and a run whose
status is not "completed" lowers the completion rate. Numbers stay separate; nothing is ranked.
"""

import json
import statistics
from pathlib import Path

from .briefs import load_briefs
from .scoring import RUBRIC, human_report, technical_report

COMPLETED = {"completed", "complete", "succeeded", "success", "done"}


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from None


def _first(mapping, *keys):
    for key in keys:
        if mapping.get(key) is not None:
            return mapping[key]
    return None


def load_run(directory, strict_contact=False):
    directory = Path(directory)
    manifest = _read(directory / "manifest.json") if (directory / "manifest.json").is_file() else {}
    technical = None
    if (directory / "technical.json").is_file():
        technical = _read(directory / "technical.json")
        if technical.get("kind") != "technical":
            raise ValueError(f"{directory / 'technical.json'} is not a technical report")
    elif (directory / "inspection.json").is_file():
        technical = technical_report(_read(directory / "inspection.json"), strict_contact=strict_contact)
    humans = []
    for path in sorted(directory.glob("human*.json")):
        data = _read(path)
        humans.append(data if data.get("kind") == "human" else human_report(data))
    status = manifest.get("status") or ("completed" if technical else "missing")
    elapsed = _first(manifest, "elapsed_seconds", "elapsed")
    waiting = manifest.get("awaiting_approval_seconds") or 0
    return {
        "run": directory.name,
        "status": status,
        "model": manifest.get("model"),
        "turns": _first(manifest, "turns", "steps"),
        "tokens": _first(manifest, "tokens", "total_tokens"),
        "elapsed": elapsed,
        "active": elapsed - waiting if elapsed is not None else None,
        "technical": technical,
        "humans": humans,
    }


def _median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def summarize_runs(runs):
    total = len(runs)
    completed = sum(1 for r in runs if str(r["status"]).lower() in COMPLETED)
    all_gates = sum(1 for r in runs if r["technical"] and r["technical"]["passed"] == r["technical"]["total"])
    shares = [r["technical"]["passed"] / r["technical"]["total"] for r in runs if r["technical"]]
    scores = [h["score"] for r in runs for h in r["humans"]]
    gaps = {dimension: 0.0 for dimension in RUBRIC}
    reviewed_twice = 0
    for run in runs:
        if len(run["humans"]) >= 2:
            reviewed_twice += 1
            for dimension in RUBRIC:
                values = [h["scores"][dimension] for h in run["humans"]]
                gaps[dimension] = max(gaps[dimension], max(values) - min(values))
    statuses = {}
    for run in runs:
        statuses[run["status"]] = statuses.get(run["status"], 0) + 1
    return {
        "runs": total,
        "statuses": dict(sorted(statuses.items())),
        "completion_rate": round(completed / total, 3) if total else None,
        "all_gates_pass_rate": round(all_gates / total, 3) if total else None,
        "mean_gate_share": round(statistics.fmean(shares), 3) if shares else None,
        "human": {
            "reviews": len(scores),
            "mean": round(statistics.fmean(scores), 2) if scores else None,
            "stdev": round(statistics.stdev(scores), 2) if len(scores) >= 2 else None,
            "runs_with_two_reviewers": reviewed_twice,
            "max_reviewer_gap": gaps if reviewed_twice else None,
        },
        "median_elapsed_s": _median(r["elapsed"] for r in runs),
        "median_active_s": _median(r["active"] for r in runs),
        "median_tokens": _median(r["tokens"] for r in runs),
        "median_turns": _median(r["turns"] for r in runs),
        "models": sorted({r["model"] for r in runs if r["model"]}),
    }


def summarize(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"{root}: runs directory not found")
    strict = {b["id"]: b.get("strict_contact", False) for b in load_briefs()}
    rows, by_config = [], {}
    for config in sorted(p for p in root.iterdir() if p.is_dir()):
        for brief in sorted(p for p in config.iterdir() if p.is_dir()):
            runs = [load_run(p, strict.get(brief.name, False)) for p in sorted(brief.iterdir()) if p.is_dir()]
            if not runs:
                continue
            rows.append({"config": config.name, "brief": brief.name, **summarize_runs(runs)})
            by_config.setdefault(config.name, []).extend(runs)
    if not rows:
        raise ValueError(f"{root}: no runs found; expected {root}/<config>/<brief>/<run>/")
    configs = [{"config": name, **summarize_runs(runs)} for name, runs in by_config.items()]
    return {
        "kind": "run_summary",
        "rows": rows,
        "configs": configs,
        "note": "Completion, gates, human ratings, latency and tokens are reported separately; there is no combined ranking.",
    }


def _cell(value, percent=False):
    if value is None:
        return "-"
    return f"{100 * value:.0f}%" if percent else f"{value:g}"


def to_markdown(summary):
    lines = [
        "| config | brief | runs | completed | all gates pass | mean gate share | human mean +/- sd | max reviewer gap | median s | median tokens |",
        "| --- | --- | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for row in summary["rows"] + [{**c, "brief": "**all briefs**"} for c in summary["configs"]]:
        human = row["human"]
        mean = (
            "-"
            if human["mean"] is None
            else f"{human['mean']:g}" + (f" +/- {human['stdev']:g}" if human["stdev"] is not None else "")
        )
        gap = "-"
        if human["max_reviewer_gap"]:
            worst = max(human["max_reviewer_gap"].items(), key=lambda item: item[1])
            gap = f"{worst[1]:g} ({worst[0]})"
        lines.append(
            f"| {row['config']} | {row['brief']} | {row['runs']} | {_cell(row['completion_rate'], True)} | "
            f"{_cell(row['all_gates_pass_rate'], True)} | {_cell(row['mean_gate_share'], True)} | {mean} | {gap} | "
            f"{_cell(row['median_elapsed_s'])} | {_cell(row['median_tokens'])} |"
        )
    return "\n".join(lines) + "\n\n" + summary["note"] + "\n"
