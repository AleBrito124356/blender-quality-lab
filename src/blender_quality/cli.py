import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .scoring import RUBRIC, human_report, technical_report


def main():
    parser = argparse.ArgumentParser(description="Blender Quality Lab â€” recipes and transparent evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("recipe", choices=["product", "abstract", "interior"])
    build.add_argument("--render", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("scene", type=Path)
    for p in [build, inspect]:
        p.add_argument("--blender", default=shutil.which("blender"))
        p.add_argument("--output", type=Path, required=True)
    score = sub.add_parser("score")
    score.add_argument("inspection", type=Path)
    score.add_argument("--strict", action="store_true")
    review = sub.add_parser("review")
    review.add_argument("ratings", type=Path)
    sub.add_parser("rubric")
    compare = sub.add_parser("compare")
    compare.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command in {"build", "inspect"}:
        if not args.blender:
            parser.error("Pass --blender /path/to/blender or add Blender to PATH")
        scripts = Path(__file__).parent / "scripts"
        if args.command == "build":
            args.output.mkdir(parents=True, exist_ok=True)
            scene_path = args.output / (args.recipe + ".blend")
            if scene_path.exists():
                parser.error(f"Refusing to overwrite {scene_path}; use a new output directory")
            command = [
                args.blender,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(scripts / "build_scene.py"),
                "--",
                "--recipe",
                args.recipe,
                "--output",
                str(args.output.resolve()),
            ]
            if args.render:
                command.append("--render")
        else:
            if not args.scene.is_file():
                parser.error("Scene file does not exist")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            command = [
                args.blender,
                "--background",
                str(args.scene.resolve()),
                "--python-exit-code",
                "1",
                "--python",
                str(scripts / "inspect_scene.py"),
                "--",
                "--output",
                str(args.output.resolve()),
            ]
        subprocess.run(command, check=True, timeout=600)
    elif args.command == "score":
        report = technical_report(json.loads(args.inspection.read_text(encoding="utf-8")))
        print(json.dumps(report, indent=2))
        if args.strict and report["passed"] != report["total"]:
            raise SystemExit(1)
    elif args.command == "review":
        print(json.dumps(human_report(json.loads(args.ratings.read_text(encoding="utf-8"))), indent=2))
    elif args.command == "rubric":
        print(
            json.dumps(
                {
                    "reviewer": "YOUR_NAME",
                    "evidence": "render.png",
                    "scores": dict.fromkeys(RUBRIC, None),
                    "notes": "",
                    "dimensions": RUBRIC,
                },
                indent=2,
            )
        )
    else:
        rows = []
        for path in args.reports:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("schema_version") != 1 or report.get("kind") not in {"technical", "human"}:
                parser.error(f"{path} is not a scored report")
            rows.append({"file": str(path), **report})
        print(
            json.dumps(
                {"reports": rows, "note": "No combined ranking: technical checks and human ratings differ."},
                indent=2,
            )
        )
