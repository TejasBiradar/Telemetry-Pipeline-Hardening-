"""Fetch a remote git repo into a temporary directory for analysis.

The clone is ephemeral: callers must clean it up. Product storage keeps only
``git_url`` / ``git_ref`` metadata, not the tree.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_REMOTE = re.compile(r"^(https?://|git@|ssh://|file://)", re.IGNORECASE)


@dataclass(frozen=True)
class GitCheckout:
    """Temporary clone root and the subdirectory to analyze."""

    repo_root: Path
    analyze_root: Path
    cleanup_dir: Path


def looks_like_git_url(value: str) -> bool:
    return bool(_REMOTE.match(value.strip()))


def shallow_clone(
    git_url: str,
    *,
    git_ref: str = "HEAD",
    source_subdir: str = "",
) -> GitCheckout:
    """Shallow-clone ``git_url`` and return paths under a temp directory.

    ``git_ref`` may be ``HEAD`` (default branch) or a branch/tag name.
    Raises ``ValueError`` for bad input, ``RuntimeError`` if git fails.
    """
    url = git_url.strip()
    if not url:
        raise ValueError("git_url is empty")
    if not looks_like_git_url(url):
        local = Path(url)
        if local.exists():
            url = local.resolve().as_uri()
        else:
            raise ValueError(
                "git_url must be a remote URL (https/ssh/file) or an existing git path"
            )

    tmp = Path(tempfile.mkdtemp(prefix="teleguard-git-"))
    dest = tmp / "repo"
    ref = git_ref.strip() or "HEAD"

    clone_cmd = ["clone", "--depth", "1"]
    if ref.upper() != "HEAD":
        clone_cmd.extend(["--branch", ref])
    clone_cmd.extend([url, str(dest)])

    try:
        _run_git(clone_cmd, cwd=tmp)
    except RuntimeError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    analyze = dest
    sub = source_subdir.strip().lstrip("./")
    if sub:
        analyze = dest / sub
        if not analyze.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
            raise FileNotFoundError(f"source_subdir not found in repo: {sub}")

    return GitCheckout(repo_root=dest, analyze_root=analyze, cleanup_dir=tmp)


def _run_git(args: list[str], *, cwd: Path) -> None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git clone timed out") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
