"""Regenerate index.json: one entry per archived file with a sha256 digest.

Covers mirror/, research-inbox/ and untracked/. Run after any of those trees
changes. Stdlib only.

Usage:
    python scripts/build_index.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
TREES = ["mirror", "research-inbox", "untracked"]

MAIN_CHECKOUT = "F:/Projects/cymatix-context"
PHASE2_WORKTREE = (
    "F:/Projects/cymatix-context/.claude/worktrees/wave-1-semantic-ranking-5f1dab"
)

STAMP_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def read_source_commit() -> str | None:
    manifest = REPO_ROOT / "mirror" / "MIRROR.md"
    if not manifest.exists():
        return None
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.startswith("- Source commit:"):
            return line.split(":", 1)[1].strip()
    return None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def classify(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    suffix = name[name.rfind("."):] if "." in name else ""
    if rel.startswith("research-inbox/"):
        return "tooling" if suffix == ".py" else "research"
    if suffix == ".py":
        return "tooling"
    if suffix == ".md":
        return "doc"
    if suffix == ".toml" or name == ".gitkeep":
        return "data"
    if rel.startswith("mirror/docs/") and "/data/" in rel:
        return "data"
    return "receipt"


def stamp_of(rel: str) -> str | None:
    match = STAMP_RE.search(rel.rsplit("/", 1)[-1])
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def source_of(rel: str) -> str:
    """Where the file came from: repo-relative for mirrored files, absolute otherwise."""
    if rel == "mirror/MIRROR.md":
        return "scripts/mirror_from_main.py"
    if rel.startswith("mirror/"):
        return rel[len("mirror/"):]
    if rel.startswith("research-inbox/"):
        return f"{MAIN_CHECKOUT}/{rel}"
    if rel.startswith("untracked/benchmarks/results/"):
        return f"{MAIN_CHECKOUT}/benchmarks/results/{rel.rsplit('/', 1)[-1]}"
    if rel.startswith("untracked/erb-phase2-tooling/"):
        tail = rel[len("untracked/erb-phase2-tooling/"):]
        if tail.startswith("pool_depth_ck_"):
            return f"{PHASE2_WORKTREE}/benchmarks/dogfood/erb/receipts/{tail}"
        if tail.endswith(".json"):
            return f"{PHASE2_WORKTREE}/benchmarks/dogfood/erb/receipts/{tail}"
        return f"{PHASE2_WORKTREE}/benchmarks/dogfood/erb/{tail}"
    return rel


def collect() -> list[dict]:
    entries: list[dict] = []
    source_commit = read_source_commit()
    for tree in TREES:
        root = REPO_ROOT / tree
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(REPO_ROOT).as_posix()
            entries.append(
                {
                    "path": rel,
                    "kind": classify(rel),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_of(path),
                    "source": source_of(rel),
                    "source_commit": (
                        source_commit
                        if rel.startswith("mirror/") and rel != "mirror/MIRROR.md"
                        else None
                    ),
                    "stamp": stamp_of(rel),
                }
            )
    return entries


def main() -> int:
    entries = collect()
    document = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_commit": read_source_commit(),
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "files": entries,
    }
    INDEX_PATH.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"indexed {document['file_count']} files, {document['total_bytes']} bytes")
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    for kind in sorted(counts):
        print(f"  {kind}: {counts[kind]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
