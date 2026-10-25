"""Beside-the-job watcher agent (MinIO stage folders → checks → results)."""

from teleguard.agent.runner import process_all_once, process_once, run_loop

__all__ = ["process_all_once", "process_once", "run_loop"]
