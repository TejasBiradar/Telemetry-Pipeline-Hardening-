"""CLI: onboard client pipeline source (metadata only).

Local:
    python -m teleguard.onboard --source pipelines/user_behavior/src --name "UB"

Git remote:
    python -m teleguard.onboard --git-url https://github.com/org/repo.git \\
        --git-ref main --source-subdir src --name "UB"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from teleguard.onboard.code import DEFAULT_STORE, onboard_pipeline, save_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze client pipeline source (local or git) and store metadata only."
    )
    parser.add_argument("--source", type=Path, default=None, help="Local source root")
    parser.add_argument("--git-url", default=None, help="Git remote URL to shallow-clone")
    parser.add_argument("--git-ref", default="HEAD", help="Branch or tag (default: HEAD)")
    parser.add_argument(
        "--source-subdir",
        default="",
        help="Subdirectory inside the repo that holds pipeline code",
    )
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--entry", default="run.run", help="module.function entry (Python)")
    parser.add_argument("--adapter", default=None, help="python_pandas | sql (auto if omitted)")
    parser.add_argument("--description", default="", help="Short description")
    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE,
        help=f"Metadata store root (default: {DEFAULT_STORE})",
    )
    args = parser.parse_args(argv)

    try:
        record = onboard_pipeline(
            name=args.name,
            entry=args.entry,
            adapter=args.adapter,
            description=args.description,
            source_path=args.source,
            git_url=args.git_url,
            git_ref=args.git_ref,
            source_subdir=args.source_subdir,
        )
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    path = save_record(record, store_root=args.store)
    print(f"onboarded {record.pipeline_id}")
    print(f"  name: {record.name}")
    if record.git_url:
        print(f"  git_url: {record.git_url} (ref={record.git_ref or 'HEAD'})")
        if record.source_subdir:
            print(f"  source_subdir: {record.source_subdir}")
    else:
        print(f"  source (reference only): {record.source_path}")
    print(f"  adapter: {record.adapter}")
    print(f"  stages ({len(record.stages)}): {', '.join(record.stages) or '(none)'}")
    print(f"  findings: {len(record.findings)}")
    print(f"  metadata: {path}")
    print("  stage_status: all pending (confirm in a later step)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
