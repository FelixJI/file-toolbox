"""Stable workflow interface for repository CI and release automation."""

from __future__ import annotations

import argparse

try:
    from scripts.automation_core import Automation
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from automation_core import Automation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    ci = commands.add_parser("ci")
    ci.add_argument("--event", choices=("pull_request", "push"), required=True)
    ci.add_argument("--source-sha", required=True)
    ci.add_argument(
        "--phase",
        choices=("full", "plan", "prepare", "shard", "finalize"),
        default="full",
    )
    ci.add_argument("--lane")
    ci.add_argument("--reports-dir", default="build/automation/lane-reports")

    release = commands.add_parser("release")
    release_commands = release.add_subparsers(dest="release_command", required=True)
    prepare = release_commands.add_parser("prepare")
    prepare.add_argument("--bump", choices=("patch", "minor", "major"), required=True)
    for name in ("stage", "publish"):
        action = release_commands.add_parser(name)
        action.add_argument("--candidate-dir", required=True)
        action.add_argument("--source-sha", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    automation = Automation.for_repository()
    if args.command == "ci":
        if args.phase == "full":
            automation.ci(event=args.event, source_sha=args.source_sha)
        elif args.phase == "plan":
            automation.ci_plan(event=args.event, source_sha=args.source_sha)
        elif args.phase == "prepare":
            automation.ci_prepare(event=args.event, source_sha=args.source_sha)
        elif args.phase == "shard":
            if not args.lane:
                raise SystemExit("--lane is required for --phase shard")
            automation.ci_shard(
                event=args.event,
                source_sha=args.source_sha,
                lane=args.lane,
            )
        else:
            automation.ci_finalize(
                event=args.event,
                source_sha=args.source_sha,
                reports_dir=args.reports_dir,
            )
    elif args.release_command == "prepare":
        automation.prepare(bump=args.bump)
    elif args.release_command == "stage":
        automation.stage(candidate_dir=args.candidate_dir, source_sha=args.source_sha)
    else:
        automation.publish(candidate_dir=args.candidate_dir, source_sha=args.source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
