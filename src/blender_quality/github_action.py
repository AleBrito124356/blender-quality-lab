"""The loop behind action.yml: check every matching .blend, write the job summary, set the outputs.

    python -m blender_quality.github_action --files "**/*.blend" --strict true --reports DIR

Used by the composite GitHub Action at the repository root; not part of the stable API. It runs
the same pipeline as `blender-quality check` for each file, appends every report.md to
$GITHUB_STEP_SUMMARY, annotates failed gates, and writes `checked`, `failed`, `errors` and
`reports` to $GITHUB_OUTPUT. Exit code 1 when a file could not be checked, or, in strict mode,
when a gate failed.
"""

import argparse
import glob
import os
import sys
from pathlib import Path

from .pipeline import InputError, check_scene
from .runner import BlenderError


def matching_files(patterns, root):
    """Existing .blend files matching any of the newline- or space-separated glob patterns."""
    found = set()
    for pattern in patterns.split():
        for match in glob.glob(pattern, root_dir=root, recursive=True):
            path = Path(root, match)
            if path.is_file() and path.suffix.lower() == ".blend":
                found.add(Path(match).as_posix())
    return sorted(found)


def report_folder(reports, file):
    """reports/<file>.quality, kept inside `reports` even for absolute or ../ patterns."""
    path = Path(file)
    parts = path.parts[1:] if path.anchor else path.parts
    parts = ["_" if part in {"..", "."} else part for part in parts]
    return Path(reports, *parts[:-1], parts[-1] + ".quality")


def annotation(level, file, title, message):
    """A GitHub workflow command; newlines and % must be escaped in the message."""
    text = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    title = title.replace("%", "%25").replace(",", "%2C").replace(":", "%3A")
    return f"::{level} file={file},title={title}::{text}"


def summary_table(rows):
    lines = ["## Blender Quality Lab", "", "| File | Gates | Result |", "| --- | --: | --- |"]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['gates']} | {row['result']} |")
    return "\n".join(lines) + "\n\n"


def append(path, text):
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def main(argv=None, env=None):
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(prog="python -m blender_quality.github_action")
    parser.add_argument(
        "--files", default="**/*.blend", help="glob patterns, separated by spaces or newlines"
    )
    parser.add_argument("--strict", default="true", help="'true' fails the step when a gate fails")
    parser.add_argument("--subject-collection", default="")
    parser.add_argument("--reports", type=Path, required=True, help="folder for the <file>.quality/ reports")
    parser.add_argument("--blender", help="Blender executable or Python with bpy (default: this Python)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="folder the globs are relative to")
    args = parser.parse_args(argv)
    strict = args.strict.strip().lower() in {"true", "1", "yes", "on"}
    blender = args.blender or sys.executable
    files = matching_files(args.files, args.root)
    rows, sections, failed, errors = [], [], 0, 0
    if not files:
        print(
            annotation("warning", "action.yml", "blender-quality", f"No .blend file matches {args.files!r}")
        )
    for file in files:
        output_dir = report_folder(args.reports, file)
        try:
            report = check_scene(
                args.root / file,
                output_dir=output_dir,
                blender=blender,
                subject_collection=args.subject_collection or None,
            )
        except (BlenderError, InputError, ValueError, OSError) as exc:
            errors += 1
            tail = "\n".join(getattr(exc, "output_tail", []) or [])
            print(annotation("error", file, "blender-quality: could not check", f"{exc}\n{tail}".strip()))
            rows.append({"file": file, "gates": "-", "result": "could not be checked"})
            fence = f"\n\n```text\n{tail}\n```" if tail else ""
            sections.append(f"## `{file}`\n\nCould not be checked: {exc}{fence}\n\n")
            continue
        gates = report["gates"]
        level = "error" if strict else "warning"
        for gate in report["failed_gates"]:
            if not gate.get("blocked_by"):
                print(
                    annotation(
                        level, file, f"blender-quality gate {gate['id']}", gate["detail"] or gate["id"]
                    )
                )
        if not report["all_gates_passed"]:
            failed += 1
        result = "all gates pass" if report["all_gates_passed"] else "gate failed"
        rows.append({"file": file, "gates": f"{gates['passed']}/{gates['total']}", "result": result})
        sections.append(f"`{file}`\n\n{report['markdown']}\n")
        print(f"{file}: {gates['passed']}/{gates['total']} gates passed")
    append(env.get("GITHUB_STEP_SUMMARY"), summary_table(rows) + "".join(sections))
    outputs = {"checked": len(files) - errors, "failed": failed, "errors": errors, "reports": args.reports}
    append(env.get("GITHUB_OUTPUT"), "".join(f"{key}={value}\n" for key, value in outputs.items()))
    return 1 if errors or (strict and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
