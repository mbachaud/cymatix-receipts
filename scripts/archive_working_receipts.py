"""Copy a Cymatix Context checkout's working-tree receipts into untracked/.

Once the code repository stops tracking ``benchmarks/dogfood/**/receipts*/``
(it ignores them instead), new receipts exist only in the working tree that
wrote them. This copies every file under a ``receipts*`` directory of
``benchmarks/`` in ``--source`` to ``untracked/<same relative path>`` here,
skipping files already archived byte-identically and refusing to overwrite an
archived file whose bytes differ (a receipt is immutable; a changed file under
the same name is a new run and needs a new name). ``build_index.py`` picks the
copies up.

Usage:
    python scripts/archive_working_receipts.py --source <path-to-checkout-or-worktree> [--dry-run]

Stdlib only. Windows friendly.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST = REPO_ROOT / "untracked"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def receipt_files(source: Path) -> list[Path]:
    root = source / "benchmarks"
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and any(part.startswith("receipts") for part in p.relative_to(source).parts[:-1])
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    source = Path(args.source)
    if not (source / "benchmarks").is_dir():
        raise SystemExit(f"no benchmarks/ under {source}")

    copied = same = 0
    conflicts = []
    for src in receipt_files(source):
        rel = src.relative_to(source)
        mirrored = REPO_ROOT / "mirror" / rel
        if mirrored.exists() and sha256(mirrored) == sha256(src):
            same += 1  # already archived by the pinned mirror/ export
            continue
        dst = DEST / rel
        if dst.exists():
            if sha256(dst) == sha256(src):
                same += 1
            else:
                conflicts.append(rel.as_posix())
            continue
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            if sha256(dst) != sha256(src):
                raise SystemExit(f"copy mismatch: {dst}")
        copied += 1
    verb = "would copy" if args.dry_run else "copied"
    print(f"{verb} {copied}, already archived {same}, conflicts {len(conflicts)}")
    for rel in conflicts:
        print(f"  CONFLICT (archived bytes differ): {rel}", file=sys.stderr)
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
