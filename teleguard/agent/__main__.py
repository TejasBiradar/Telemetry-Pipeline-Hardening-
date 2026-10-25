"""CLI for the watcher agent.

    # Watch every onboarded pipeline that has an output store
    python -m teleguard.agent --poll 5

    # Or one pipeline
    python -m teleguard.agent --pipeline-id <uuid> --once
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from teleguard.agent.runner import process_all_once, process_once, run_loop
from teleguard.onboard.code import DEFAULT_STORE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Driftline stage-output watcher agent")
    parser.add_argument(
        "--pipeline-id",
        default=None,
        help="UUID to watch; omit to watch all onboarded pipelines with an output store",
    )
    parser.add_argument("--poll", type=float, default=5.0, help="Seconds between scans")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process new objects once and exit",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Control-plane base URL (POST results). Omit to write local store only.",
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.once:
            if args.pipeline_id:
                runs = process_once(
                    args.pipeline_id,
                    store_root=args.store,
                    api_url=args.api_url,
                )
            else:
                runs = process_all_once(store_root=args.store, api_url=args.api_url)
            print(f"processed {len(runs)} new object(s)")
            for run in runs:
                print(f"  {run.object_key}: fail={run.failed} pass={run.passed}")
            return 0
        run_loop(
            args.pipeline_id,
            poll_seconds=args.poll,
            store_root=args.store,
            api_url=args.api_url,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
