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
    # 2026-09-02: the seven per-corpus receipt trees below were NOT mirrored
    # before this date. They were found missing while preparing to untrack
    # benchmarks/dogfood/**/receipts/ from the main repo -- mirroring without
    # them would have dropped ~640k lines of evidence (muloc 237k, enronqa
    # 118k, enronqa_padded 92k, financebench 68k, and three locomo trees).
    "benchmarks/dogfood/enronqa/receipts",
    "benchmarks/dogfood/enronqa_padded/receipts",
    "benchmarks/dogfood/financebench/receipts",
    "benchmarks/dogfood/locomo/receipts",
    "benchmarks/dogfood/locomo_obs/receipts",
    "benchmarks/dogfood/locomo_obs_ctl/receipts",
    "benchmarks/dogfood/muloc/receipts",
    "benchmarks/dogfood/code/receipts",
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


def tracked_receipt_files(source: Path, ref: str) -> list[str]:
    """Every file at `ref` with a path component starting with `receipts`.

    Covers `receipts/` and siblings such as `receipts_w32/` at any depth, so a
    receipt tree added upstream after DIR_SPECS was written is still found.
    """
    out = git(source, "ls-tree", "-r", "--name-only", ref, "--", "benchmarks/")
    return sorted(
        line for line in out.splitlines()
        if any(part.startswith("receipts") for part in line.split("/")[:-1])
    )


def discovered_receipt_dirs(files: list[str]) -> list[str]:
    """The receipt directory (path up to its `receipts*` component) of each file."""
    dirs = set()
    for path in files:
        parts = path.split("/")
        for i, part in enumerate(parts[:-1]):
            if part.startswith("receipts"):
                dirs.add("/".join(parts[: i + 1]))
                break
    return sorted(dirs)


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
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="replace mirror/ even when the ref tracks fewer receipt files than it holds",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not (source / ".git").exists():
        raise SystemExit(f"not a git checkout: {source}")

    if not args.no_fetch and args.ref.startswith("origin/"):
        git(source, "fetch", "origin", args.ref.split("/", 1)[1])

    sha = git(source, "rev-parse", args.ref).strip()

    # 2026-10-04: DIR_SPECS missed four receipt trees added upstream on
    # 2026-09-04 (coderag_solutions, coderag_docs, cosqa, swebench). Discover
    # every receipt tree from the ref itself; DIR_SPECS stays as a floor.
    receipt_files = tracked_receipt_files(source, args.ref)
    specs = sorted(set(DIR_SPECS) | set(discovered_receipt_dirs(receipt_files)))

    # Shrink guard (2026-10-04): once the code repo stops tracking its receipt
    # trees, exporting a later ref would find none and the wholesale replace
    # below would empty the receipt half of mirror/. Refuse unless asked.
    held = [p for p in walk_files(MIRROR_DIR)
            if any(part.startswith("receipts")
                   for part in p.relative_to(MIRROR_DIR).parts[:-1])] if MIRROR_DIR.exists() else []
    if len(receipt_files) < len(held) and not args.allow_shrink:
        raise SystemExit(
            f"{args.ref} tracks {len(receipt_files)} receipt files but mirror/ holds {len(held)}; "
            "the code repo has likely untracked them. Keep this mirror (its pinned commit is "
            "the last export) and archive new receipts with scripts/archive_working_receipts.py, "
            "or pass --allow-shrink to replace mirror/ anyway.")

    if MIRROR_DIR.exists():
        shutil.rmtree(MIRROR_DIR)
    MIRROR_DIR.mkdir(parents=True)

    export(source, args.ref, specs, MIRROR_DIR)
    for directory in FLAT_JSON_DIRS:
        export(source, args.ref, flat_json_files(source, args.ref, directory), MIRROR_DIR)

    missing = [p for p in receipt_files if not (MIRROR_DIR / p).is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} tracked receipt files absent from the mirror, "
                         f"first: {missing[:5]}")

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
    for spec in specs:
        count = len([f for f in files if str(f.relative_to(MIRROR_DIR)).replace("\\", "/").startswith(spec + "/")])
        lines.append(f"- `{spec}/` ({count} files)")
    lines.append(f"- tracked receipt files at the ref (any `receipts*` dir): "
                 f"{len(receipt_files)}, all present")
    flat_total = sum(len(flat_json_files(source, args.ref, d)) for d in FLAT_JSON_DIRS)
    for directory in FLAT_JSON_DIRS:
        lines.append(f"- `{directory}/*.json` ({flat_total} files, non-recursive)")
    lines.append("")

    (MIRROR_DIR / "MIRROR.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"mirrored {len(files)} files, {total_bytes} bytes, from {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
