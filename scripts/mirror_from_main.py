"""Regenerate mirror/ from a Cymatix Context checkout at a pinned git ref.

Exports the tracked receipt corpus straight out of a commit (never the working
tree) so the mirror is reproducible and attributable to a single sha.

Usage:
    python scripts/mirror_from_main.py --source <path-to-checkout> [--ref origin/master]

Stdlib only. Windows friendly.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

REPO_ROOT = Path(__file__).resolve().parent.parent
MIRROR_DIR = REPO_ROOT / "mirror"

DEFAULT_SOURCE = (
    r"F:/Projects/cymatix-context/.claude/worktrees/website-reconnection-errors-fb70d7"
)
SOURCE_REPO_URL = "https://github.com/mbachaud/Cymatix-Context"

# Whole directories exported recursively.
DIR_SPECS = [
    "benchmarks/dogfood/erb/receipts",
    "benchmarks/dogfood/receipts",
    "benchmarks/dogfood/receipts_w32",
    "benchmarks/snow/results",
    "benchmarks/results/faithfulness",
    "docs/benchmarks",
    "docs/research/data",
]

# Non-recursive: the arm/baseline/ladder JSON receipts sitting directly in
# benchmarks/dogfood/ (the .py harnesses at that level are not receipts).
FLAT_JSON_DIRS = ["benchmarks/dogfood"]


def git(source: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
        creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr}")
    return proc.stdout


def flat_json_files(source: Path, ref: str, directory: str) -> list[str]:
    out = git(source, "ls-tree", "--name-only", ref, "--", directory + "/")
    return sorted(
        line
        for line in out.splitlines()
        if line.strip().endswith(".json")
    )


def export(source: Path, ref: str, specs: list[str], dest: Path) -> None:
    """Stream `git archive` for the given pathspecs into dest."""
    if not specs:
        return
    proc = subprocess.Popen(
        ["git", "-C", str(source), "archive", "--format=tar", ref, "--", *specs],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=NO_WINDOW,
    )
    assert proc.stdout is not None
    payload = proc.stdout.read()
    stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit(f"git archive failed for {specs[:3]}...:\n{stderr}")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tar:
        try:
            tar.extractall(path=dest, filter="data")
        except TypeError:  # Python < 3.12
            tar.extractall(path=dest)


def walk_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--ref", default="origin/master")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="skip `git fetch` in the source checkout",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not (source / ".git").exists():
        raise SystemExit(f"not a git checkout: {source}")

    if not args.no_fetch and args.ref.startswith("origin/"):
        git(source, "fetch", "origin", args.ref.split("/", 1)[1])

    sha = git(source, "rev-parse", args.ref).strip()

    if MIRROR_DIR.exists():
        shutil.rmtree(MIRROR_DIR)
    MIRROR_DIR.mkdir(parents=True)

    export(source, args.ref, DIR_SPECS, MIRROR_DIR)
    for directory in FLAT_JSON_DIRS:
        export(source, args.ref, flat_json_files(source, args.ref, directory), MIRROR_DIR)

    files = walk_files(MIRROR_DIR)
    total_bytes = sum(f.stat().st_size for f in files)

    lines = [
        "# Mirror manifest",
        "",
        "`mirror/` is a byte-for-byte export of the tracked receipt corpus from the",
        "Cymatix Context repository, taken from a pinned commit rather than a working",
        "tree. Regenerate it with `python scripts/mirror_from_main.py`.",
        "",
        f"- Source repo: {SOURCE_REPO_URL}",
        f"- Source ref: {args.ref}",
        f"- Source commit: {sha}",
        f"- Export date: {date.today().isoformat()}",
        f"- File count: {len(files)}",
        f"- Total bytes: {total_bytes}",
        "",
        "## Exported paths",
        "",
    ]
    for spec in DIR_SPECS:
        count = len([f for f in files if str(f.relative_to(MIRROR_DIR)).replace("\\", "/").startswith(spec + "/")])
        lines.append(f"- `{spec}/` ({count} files)")
    flat_total = sum(len(flat_json_files(source, args.ref, d)) for d in FLAT_JSON_DIRS)
    for directory in FLAT_JSON_DIRS:
        lines.append(f"- `{directory}/*.json` ({flat_total} files, non-recursive)")
    lines.append("")

    (MIRROR_DIR / "MIRROR.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"mirrored {len(files)} files, {total_bytes} bytes, from {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
