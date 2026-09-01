"""Recompute sha256 digests and report drift against index.json.

Exit code 0 when the archive matches the index, 1 when it does not.

Usage:
    python scripts/verify_index.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
TREES = ["mirror", "research-inbox", "untracked"]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if not INDEX_PATH.exists():
        print("index.json missing; run scripts/build_index.py")
        return 1
    document = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    indexed = {entry["path"]: entry for entry in document["files"]}

    on_disk = set()
    for tree in TREES:
        root = REPO_ROOT / tree
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                on_disk.add(path.relative_to(REPO_ROOT).as_posix())

    missing = sorted(set(indexed) - on_disk)
    untracked = sorted(on_disk - set(indexed))
    changed: list[str] = []

    for rel in sorted(set(indexed) & on_disk):
        path = REPO_ROOT / rel
        entry = indexed[rel]
        if path.stat().st_size != entry["bytes"] or sha256_of(path) != entry["sha256"]:
            changed.append(rel)

    for label, rows in (
        ("missing from disk", missing),
        ("present but not indexed", untracked),
        ("digest or size drift", changed),
    ):
        if rows:
            print(f"{label}: {len(rows)}")
            for rel in rows[:20]:
                print(f"  {rel}")
            if len(rows) > 20:
                print(f"  ... and {len(rows) - 20} more")

    if missing or untracked or changed:
        print("FAIL: index.json does not match the archive")
        return 1
    print(f"OK: {len(indexed)} files match index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
