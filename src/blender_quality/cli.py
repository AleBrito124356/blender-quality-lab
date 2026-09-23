import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import diff as scene_diff
from . import summarize as run_summary
from .briefs import brief_text, get_brief, load_briefs
from .describe import describe, to_markdown
from .image_metrics import measure_file
from .runner import (
    DEFAULT_TIMEOUT,
    BlenderError,
    blender_version,
    find_blender,
    install_candidates,
    run_blender,
)
from .scoring import RUBRIC, human_report, technical_report

SCRIPTS = Path(__file__).parent / "scripts"
RECIPES = ["product", "abstract", "interior"]


class UsageError(ValueError):
    """Bad input from the user; reported without a traceback and exit code 2."""


def read_json(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise UsageError(f"{path}: file not found") from None
    except OSError as exc:
        raise UsageError(f"{path}: cannot read ({exc.strerror or exc})") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"{path}: not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})"
        ) from None


def emit_json(data):
    print(json.dumps(data, indent=2))


def add_blender_options(parser):
    parser.add_argument(
        "--blender",
        help="Blender executable (default: $BLENDER, then PATH, then standard install folders)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"seconds before the Blender process is stopped (default {DEFAULT_TIMEOUT})",
    )
    parser.add_argument("--verbose", action="store_true", help="print Blender's own log")


def add_inspection_options(parser):
    parser.add_argument(
        "--subject",
        action="append",
        default=[],
        metavar="NAME",
        help="subject object name or glob (repeatable)",
    )
    parser.add_argument(
        "--subject-collection",
        action="append",
        default=[],
        metavar="NAME",
        help="collection holding the subject",
    )
    parser.add_argument("--scene-name", metavar="NAME", help="inspect this scene instead of the active one")
    parser.add_argument(
        "--grid", type=int, default=64, help="columns of the camera coverage grid (default 64)"
    )
    parser.add_argument(
        "--contact-scale",
        type=float,
        default=1.0,
        help="multiplier for the 5 mm contact tolerance (default 1)",
    )
    parser.add_argument(
        "--preview-percentage", type=int, default=25, help="preview size in percent (default 25)"
    )
    parser.add_argument("--preview-samples", type=int, default=16, help="preview render samples (default 16)")


def cmd_build(args):
    blender = find_blender(args.blender)
    scene_path = args.output / (args.recipe + ".blend")
    if scene_path.exists():
        raise UsageError(f"Refusing to overwrite {scene_path}; use a new output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    script_args = ["--recipe", args.recipe, "--output", args.output.resolve()]
    if args.render:
        script_args.append("--render")
    run = run_blender(
        blender.path,
        SCRIPTS / "build_scene.py",
        script_args,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    print(f"scene: {scene_path}")
    if args.render:
        print(f"render: {args.output / (args.recipe + '.png')}")
    print(f"blender: {blender.path} ({run.elapsed:.1f} s)", file=sys.stderr)
    return 0


def inspection_args(args):
    """Options forwarded to scripts/inspect_scene.py."""
    extra = []
    for name in args.subject:
        extra += ["--subject", name]
    for name in args.subject_collection:
        extra += ["--subject-collection", name]
    if args.scene_name:
        extra += ["--scene", args.scene_name]
    extra += ["--grid", str(args.grid), "--contact-scale", str(args.contact_scale)]
    return extra


def run_inspection(args, output, preview=None):
    blender = find_blender(args.blender)
    if not args.scene.is_file():
        raise UsageError(f"Scene file does not exist: {args.scene}")
    output.parent.mkdir(parents=True, exist_ok=True)
    script_args = ["--output", output.resolve(), *inspection_args(args)]
    if preview is not None:
        script_args += [
            "--preview",
            preview.resolve(),
            "--preview-percentage",
            str(args.preview_percentage),
            "--preview-samples",
            str(args.preview_samples),
        ]
    run = run_blender(
        blender.path,
        SCRIPTS / "inspect_scene.py",
        script_args,
        blend_file=args.scene.resolve(),
        timeout=args.timeout,
        verbose=args.verbose,
    )
    if not output.is_file():
        raise BlenderError("Blender finished but did not write the inspection JSON")
    print(f"blender: {blender.path} ({run.elapsed:.1f} s)", file=sys.stderr)
    return output


def cmd_inspect(args):
    run_inspection(args, args.output, args.preview)
    print(f"inspection: {args.output}")
    if args.preview:
        print(f"preview: {args.preview}")
    return 0


def cmd_doctor(args):
    report = {"blender_quality_lab": __version__, "python": sys.version.split()[0]}
    try:
        blender = find_blender(args.blender)
    except BlenderError as exc:
        report.update(blender=None, problem=str(exc))
    else:
        report.update(blender=blender.path, found_via=blender.source, version=blender_version(blender.path))
    others = [str(p) for p in install_candidates() if str(p) != report.get("blender")]
    report["other_installs"] = others
    if args.json:
        emit_json(report)
    else:
        print(f"blender-quality-lab {report['blender_quality_lab']} on Python {report['python']}")
        if report["blender"]:
            print(f"Blender: {report['blender']}")
            print(f"  found via: {report['found_via']}")
            print(f"  version:   {report['version']}")
        else:
            print(f"Blender: not found. {report['problem']}")
        for path in others:
            print(f"  also installed: {path}")
    return 0 if report["blender"] else 1


def cmd_score(args):
    report = technical_report(read_json(args.inspection), strict_contact=args.strict_contact)
    emit_json(report)
    if args.strict and report["passed"] != report["total"]:
        return 1
    return 0


def cmd_review(args):
    emit_json(human_report(read_json(args.ratings)))
    return 0


def cmd_rubric(args):
    emit_json(
        {
            "reviewer": "YOUR_NAME",
            "evidence": "render.png",
            "scores": dict.fromkeys(RUBRIC, None),
            "notes": "",
            "dimensions": RUBRIC,
        }
    )
    return 0


def cmd_measure(args):
    metrics = measure_file(args.image, grid=args.grid)
    emit_json(metrics)
    return 1 if args.strict and metrics.get("warnings") else 0


def write_report(report, fmt):
    if fmt == "json":
        emit_json(report)
    else:
        sys.stdout.write(to_markdown(report))


def cmd_describe(args):
    metrics = measure_file(args.image) if args.image else None
    report = describe(read_json(args.inspection), metrics, strict_contact=args.strict_contact)
    write_report(report, args.format)
    return 0


def cmd_check(args):
    output_dir = args.output_dir or args.scene.with_name(args.scene.stem + ".quality")
    output_dir.mkdir(parents=True, exist_ok=True)
    inspection_path = output_dir / "inspection.json"
    preview = None if args.no_preview else output_dir / "preview.png"
    run_inspection(args, inspection_path, preview)
    metrics = measure_file(preview) if preview is not None and preview.is_file() else None
    inspection = read_json(inspection_path)
    report = describe(inspection, metrics, strict_contact=args.strict_contact)
    technical = technical_report(inspection, strict_contact=args.strict_contact)
    (output_dir / "technical.json").write_text(json.dumps(technical, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(to_markdown(report), encoding="utf-8")
    (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_report(report, args.format)
    print(f"reports: {output_dir}", file=sys.stderr)
    if args.strict and technical["passed"] != technical["total"]:
        return 1
    return 0


def cmd_briefs(args):
    if args.action == "list":
        briefs = load_briefs(args.file)
        if args.json:
            emit_json(briefs)
        else:
            for brief in briefs:
                first = brief["prompt"].split(". ")[0]
                print(f"{brief['id']:<22} {brief['difficulty']:<7} {first}")
    elif args.action == "validate":
        briefs = load_briefs(args.file)
        print(f"{args.file or 'packaged briefs'}: {len(briefs)} valid briefs")
    else:
        if not args.brief_id:
            raise UsageError("briefs show needs a brief id; see `blender-quality briefs list`")
        brief = get_brief(args.brief_id, args.file)
        if args.json:
            emit_json(brief)
        elif args.prompt_only:
            print(brief["prompt"])
        else:
            sys.stdout.write(brief_text(brief))
    return 0


def cmd_diff(args):
    original = scene_diff.original_path(args.original) if args.original else None
    result = scene_diff.diff_inspections(read_json(args.before), read_json(args.after), original)
    if args.format == "md":
        sys.stdout.write(scene_diff.to_markdown(result))
    else:
        emit_json(result)
    return 1 if args.strict and not result["preserve_and_relight"]["passed"] else 0


def cmd_summarize(args):
    summary = run_summary.summarize(args.runs)
    if args.format == "md":
        sys.stdout.write(run_summary.to_markdown(summary))
    else:
        emit_json(summary)
    return 0


def cmd_compare(args):
    print("blender-quality: note: `compare` is deprecated; use `summarize RUNS_DIR`", file=sys.stderr)
    if len(args.reports) == 1 and args.reports[0].is_dir():
        emit_json(run_summary.summarize(args.reports[0]))
        return 0
    rows = []
    for path in args.reports:
        report = read_json(path)
        if report.get("schema_version") not in {1, 2} or report.get("kind") not in {"technical", "human"}:
            raise UsageError(f"{path} is not a scored report")
        rows.append({"file": str(path), **report})
    emit_json({"reports": rows, "note": "No combined ranking: technical checks and human ratings differ."})
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="blender-quality",
        description="Blender Quality Lab: recipes, vision-free scene inspection and transparent evaluation",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a recipe scene in an isolated Blender")
    build.add_argument("recipe", choices=RECIPES)
    build.add_argument("--output", type=Path, required=True, help="output directory")
    build.add_argument("--render", action="store_true", help="also render the final image")
    add_blender_options(build)
    build.set_defaults(handler=cmd_build)

    inspect = sub.add_parser("inspect", help="collect scene facts from a .blend without running its scripts")
    inspect.add_argument("scene", type=Path)
    inspect.add_argument("--output", type=Path, required=True, help="inspection JSON to write")
    inspect.add_argument("--preview", type=Path, help="also render a small preview PNG here (final engine)")
    add_inspection_options(inspect)
    add_blender_options(inspect)
    inspect.set_defaults(handler=cmd_inspect)

    doctor = sub.add_parser("doctor", help="show which Blender would be used and its version")
    doctor.add_argument("--blender", help="check this executable instead of discovering one")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=cmd_doctor)

    score = sub.add_parser("score", help="technical gates for an inspection JSON")
    score.add_argument("inspection", type=Path)
    score.add_argument("--strict", action="store_true", help="exit 1 if any gate fails")
    score.add_argument(
        "--strict-contact", action="store_true", help="make floating objects a gate instead of a warning"
    )
    score.set_defaults(handler=cmd_score)

    measure = sub.add_parser("measure", help="exposure and layout metrics of a rendered PNG (pure Python)")
    measure.add_argument("image", type=Path)
    measure.add_argument("--grid", type=int, default=8, help="cells per side of the luminance/detail grid")
    measure.add_argument("--strict", action="store_true", help="exit 1 if any exposure warning is raised")
    measure.set_defaults(handler=cmd_measure)

    describe_cmd = sub.add_parser(
        "describe", help="text report of what the camera sees, what is wrong and how to fix it"
    )
    describe_cmd.add_argument("inspection", type=Path, help="schema v2 inspection JSON")
    describe_cmd.add_argument("--image", type=Path, help="render or preview PNG to add exposure facts")
    describe_cmd.add_argument("--format", choices=["md", "json"], default="md")
    describe_cmd.add_argument("--strict-contact", action="store_true")
    describe_cmd.set_defaults(handler=cmd_describe)

    check = sub.add_parser(
        "check", help="inspect + preview render + measure + gates + report, in one isolated Blender run"
    )
    check.add_argument("scene", type=Path)
    check.add_argument("--output-dir", type=Path, help="where to write reports (default: SCENE.quality/)")
    check.add_argument("--no-preview", action="store_true", help="skip the small preview render")
    check.add_argument("--format", choices=["md", "json"], default="md")
    check.add_argument("--strict", action="store_true", help="exit 1 if any gate fails")
    check.add_argument("--strict-contact", action="store_true")
    add_inspection_options(check)
    add_blender_options(check)
    check.set_defaults(handler=cmd_check)

    review = sub.add_parser("review", help="validate a filled rubric and normalize the human score")
    review.add_argument("ratings", type=Path)
    review.set_defaults(handler=cmd_review)

    rubric = sub.add_parser("rubric", help="print an empty human rating template")
    rubric.set_defaults(handler=cmd_rubric)

    briefs = sub.add_parser("briefs", help="list, show or validate the controlled briefs")
    briefs.add_argument("action", choices=["list", "show", "validate"])
    briefs.add_argument("brief_id", nargs="?", help="brief id for `show`")
    briefs.add_argument(
        "--prompt-only", action="store_true", help="print only the prompt (for piping into a harness)"
    )
    briefs.add_argument("--json", action="store_true")
    briefs.add_argument("--file", type=Path, help="use this briefs JSON instead of the packaged one")
    briefs.set_defaults(handler=cmd_briefs)

    diff = sub.add_parser("diff", help="what changed between two inspections; checks preserve-and-relight")
    diff.add_argument("before", type=Path, help="inspection of the input scene")
    diff.add_argument("after", type=Path, help="inspection of the edited copy")
    diff.add_argument("--original", type=Path, help="the input .blend, to prove it was not overwritten")
    diff.add_argument("--format", choices=["json", "md"], default="json")
    diff.add_argument("--strict", action="store_true", help="exit 1 if the preserve-and-relight check fails")
    diff.set_defaults(handler=cmd_diff)

    summarize = sub.add_parser("summarize", help="aggregate RUNS_DIR/<config>/<brief>/<run>/ without ranking")
    summarize.add_argument("runs", type=Path)
    summarize.add_argument("--format", choices=["json", "md"], default="md")
    summarize.set_defaults(handler=cmd_summarize)

    compare = sub.add_parser("compare", help="deprecated: use summarize (still lists scored reports)")
    compare.add_argument("reports", nargs="+", type=Path)
    compare.set_defaults(handler=cmd_compare)
    return parser


def print_error(message, tail=()):
    print(f"blender-quality: error: {message}", file=sys.stderr)
    for line in tail:
        print(f"  | {line}", file=sys.stderr)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # object names can hold characters the console lacks
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except BlenderError as exc:
        print_error(str(exc), exc.output_tail)
        return 1
    except KeyError as exc:
        print_error(f"input is missing the required field {exc}")
        return 2
    except (ValueError, TypeError) as exc:
        print_error(str(exc))
        return 2
    except OSError as exc:
        print_error(f"{exc.filename or ''}: {exc.strerror or exc}".lstrip(": "))
        return 2
