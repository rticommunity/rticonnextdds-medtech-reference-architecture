#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.
"""Project-level markdown lint test.

Validates that all Markdown files not ignored by git pass markdownlint using
repository rules from ``.markdownlint.json``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _git_markdown_files() -> list[str]:
    """Return all markdown files in the project, excluding generated/cache directories.

    Uses recursive glob instead of git ls-files for consistency across environments
    (local, CI, Docker) where .git may or may not be present.
    """
    exclude_patterns = {".venv", "build", ".pytest_cache", "__pycache__", ".git"}
    files = []
    for p in PROJECT_ROOT.rglob("*.md"):
        # Skip if any path component is in exclude_patterns or is hidden
        if not any(part in exclude_patterns or part.startswith(".") for part in p.relative_to(PROJECT_ROOT).parts):
            files.append(str(p.relative_to(PROJECT_ROOT)))
    return sorted(files)


def test_markdownlint_clean() -> None:
    """All non-ignored markdown files should satisfy markdownlint rules."""
    markdownlint = shutil.which("markdownlint")
    assert markdownlint, "markdownlint executable not found on PATH"

    md_files = _git_markdown_files()
    assert md_files, "No markdown files found via git"

    result = subprocess.run(
        [
            markdownlint,
            "--config",
            ".markdownlint.json",
            *md_files,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"markdownlint found violations:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
