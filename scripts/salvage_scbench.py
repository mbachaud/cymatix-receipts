"""salvage_scbench.py -- archive the disk-only SCBench campaign pair receipts as release assets.

The Luna pilot (2026-08-08-codex-pilot) and Terra (2026-08-11-codex-terra)
campaigns of the SCBench Codex/Cymatix A/B harness (branch
codex/scbench-cymatix-ab) gitignore their pair receipts, preflight and the
Terra analysis; the only copy lives in one worktree. This script copies them
into a staging tree (sources never modified), checkpoints each sidecar
cymatix.genome.db WAL on the COPY and drops the -wal/-shm sidecars, builds one
tar per campaign (python tarfile, paths rooted at benchmarks/scbench/...),
compresses with zstandard level 12, sha256s both, round-trip verifies, and
writes captures/scbench/MANIFEST.json + release notes.

    python scripts/salvage_scbench.py build
    python scripts/salvage_scbench.py publish   # gh release create + size verify + asset URLs
    python scripts/salvage_scbench.py docs      # re-render notes/README from MANIFEST.json
"""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import zstandard as zstd

sys.stdout.reconfigure(encoding="utf-8")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ROOT = Path(__file__).resolve().parent.parent
REPO = "mbachaud/cymatix-receipts"
TAG = "scbench-campaign-receipts-2026-08"
TITLE = "SCBench Codex/Cymatix campaign pair receipts (Luna pilot + Terra, August 2026)"
SRC_WT = Path("F:/Projects/cymatix-context/.claude/worktrees/scbench-codex-ab")
SRC_BRANCH = "codex/scbench-cymatix-ab"
STAGING = Path("F:/Projects/cymatix-receipts-staging/salvage/scbench")
OUT = STAGING / "out"
CAPT = ROOT / "captures" / "scbench"
MANIFEST = CAPT / "MANIFEST.json"
CAMPAIGNS = {
    "2026-08-08-codex-pilot": {
        "label": "scbench-luna-pilot-2026-08-08",
        "items": ["pairs", "preflight.json"],
        "frozen_tag": "bench/scbench-luna-2026-08-08",
        "verdict": "Luna pilot: NOT graduated (4/8 predeclared gates fail, issue #359 decision STOP); "
                   "analysis-v2 (committed on the branch) no_detectable_difference, safety gates pass",
    },
    "2026-08-11-codex-terra": {
        "label": "scbench-terra-2026-08-11",
        "items": ["pairs", "preflight.json", "analysis-v2.json", "analysis-v2.md"],
        "frozen_tag": "bench/scbench-terra-2026-08-11",
        "verdict": "Terra v2: no_detectable_difference, all 7 safety gates pass "
                   "(head-to-head cymatix 18 / control 24 / tied 22; input-token ratio 1.13; elapsed 1.08)",
    },
}
SIDECAR_SUFFIXES = ("-wal", "-shm")
PRIVACY_NOTE = (
    "Pair receipts include Codex CLI stdout/stderr, agent run logs, workspace snapshots of the "
    "SCBench problems, and the per-pair sidecar knowledge store. They were produced by a benchmark "
    "harness against synthetic SCBench problems, not by the transparent proxy, but nothing here has "
    "been content-scanned. The repository stays private until an owner review clears it."
)


def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True, creationflags=NOWIN,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("cmd failed (%s): %s\n%s" % (r.returncode, " ".join(cmd), r.stderr))
    return r


def sha256_path(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_stats(root):
    n, b = 0, 0
    for p in root.rglob("*"):
        if p.is_file():
            n += 1
            b += p.stat().st_size
    return n, b


def checkpoint_sidecars(copy_root, src_root):
    """Checkpoint every *.db that has a -wal sibling, on the COPY, then drop -wal/-shm."""
    records = []
    for wal in sorted(copy_root.rglob("*.db-wal")):
        db = wal.with_name(wal.name[:-4])
        shm = wal.with_name(wal.name[:-4] + "-shm")
        rel = db.relative_to(copy_root).as_posix()
        src_db = src_root / db.relative_to(copy_root)
        rec = {"db": rel, "source_db_bytes": src_db.stat().st_size,
               "source_db_sha256": sha256_path(src_db), "source_wal_bytes": wal.stat().st_size}
        con = sqlite3.connect(str(db))
        try:
            ck = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            rec["wal_checkpoint"] = list(ck)
            rec["quick_check"] = con.execute("PRAGMA quick_check").fetchone()[0]
            con.execute("PRAGMA journal_mode=DELETE")
        finally:
            con.close()
        for side in (wal, shm):
            if side.exists():
                side.unlink()
        rec["archived_db_bytes"] = db.stat().st_size
        rec["archived_db_sha256"] = sha256_path(db)
        records.append(rec)
    # stray -shm without -wal
    for shm in sorted(copy_root.rglob("*.db-shm")):
        shm.unlink()
    return records


def notes_for_entry(camp, sidecars):
    frames = sum(r["wal_checkpoint"][1] for r in sidecars if r["wal_checkpoint"][1] > 0)
    same_bytes = all(r["source_db_bytes"] == r["archived_db_bytes"] for r in sidecars)
    return [
        "tar entries are rooted at benchmarks/scbench/campaigns/%s/ so they extract over a checkout of %s" % (camp, SRC_BRANCH),
        "sidecar cymatix.genome.db files were copied with their -wal, checkpointed (TRUNCATE) on the copy, "
        "then the -wal/-shm sidecars were dropped; sources untouched",
        "checkpoint result: %d WAL frames applied across %d sidecar dbs%s; the archived db differs from the "
        "source db only by the journal_mode header (WAL -> DELETE), both sha256 recorded per db"
        % (frames, len(sidecars), " (WAL already applied; db page bytes identical)" if same_bytes and frames == 0 else ""),
        "the pair receipt tree hashes *.json only (integrations/scbench/receipts.py), so the sidecar db "
        "header change does not affect verify-receipts replay",
    ]


def docs():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for c in man["captures"]:
        c["notes"] = notes_for_entry(c["campaign"], c["sidecar_dbs_checkpointed_on_copy"])
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    write_docs(man)
    print("refreshed notes + docs")


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    CAPT.mkdir(parents=True, exist_ok=True)
    head = run(["git", "-C", str(SRC_WT), "rev-parse", "HEAD"]).stdout.strip()
    branch = run(["git", "-C", str(SRC_WT), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    entries = []
    for camp, spec in CAMPAIGNS.items():
        t0 = time.time()
        rel_root = Path("benchmarks/scbench/campaigns") / camp
        src_root = SRC_WT / rel_root
        stage = STAGING / camp
        if stage.exists():
            shutil.rmtree(stage)
        copy_root = stage / rel_root
        copy_root.mkdir(parents=True)
        src_files, src_bytes = 0, 0
        dropped = []
        for item in spec["items"]:
            s, d = src_root / item, copy_root / item
            if s.is_dir():
                shutil.copytree(s, d, copy_function=shutil.copy2)
            else:
                shutil.copy2(s, d)
            for p in ([s] if s.is_file() else s.rglob("*")):
                if p.is_file():
                    src_files += 1
                    src_bytes += p.stat().st_size
                    if p.name.endswith(SIDECAR_SUFFIXES):
                        dropped.append({"path": p.relative_to(src_root).as_posix(), "bytes": p.stat().st_size})
        sidecars = checkpoint_sidecars(copy_root, src_root)
        arc_files, arc_bytes = tree_stats(copy_root)
        tar_path = OUT / (spec["label"] + ".tar")
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tf:
            for p in sorted(x for x in stage.rglob("*") if x.is_file()):
                tf.add(p, arcname=p.relative_to(stage).as_posix(), recursive=False)
        tar_bytes, tar_sha = tar_path.stat().st_size, sha256_path(tar_path)
        zst_path = OUT / (spec["label"] + ".tar.zst")
        cctx = zstd.ZstdCompressor(level=12, threads=-1)
        with open(tar_path, "rb") as fi, open(zst_path, "wb") as fo:
            cctx.copy_stream(fi, fo)
        zst_bytes, zst_sha = zst_path.stat().st_size, sha256_path(zst_path)
        h = hashlib.sha256()
        with open(zst_path, "rb") as fi:
            for chunk in zstd.ZstdDecompressor().read_to_iter(fi, read_size=1 << 20):
                h.update(chunk)
        roundtrip_ok = h.hexdigest() == tar_sha
        entry = {
            "label": spec["label"],
            "campaign": camp,
            "release_tag": TAG,
            "asset_name": zst_path.name,
            "asset_url": None,
            "source_worktree": str(SRC_WT),
            "source_branch": branch if branch != "HEAD" else SRC_BRANCH,
            "source_head": head,
            "frozen_tag": spec["frozen_tag"],
            "source_path": str(src_root),
            "source_items": spec["items"],
            "source_files": src_files,
            "source_bytes": src_bytes,
            "dropped_sidecars": {"count": len(dropped), "bytes": sum(d["bytes"] for d in dropped)},
            "sidecar_dbs_checkpointed_on_copy": sidecars,
            "archived_files": arc_files,
            "archived_bytes": arc_bytes,
            "tar_bytes": tar_bytes,
            "sha256_tar": tar_sha,
            "zst_bytes": zst_bytes,
            "sha256_zst": zst_sha,
            "ratio": round(tar_bytes / zst_bytes, 2),
            "roundtrip_ok": roundtrip_ok,
            "seconds": round(time.time() - t0, 1),
            "verdict": spec["verdict"],
            "notes": notes_for_entry(camp, sidecars),
        }
        entries.append(entry)
        print("%-32s files %5d -> %5d  bytes %11d -> tar %11d -> zst %10d (x%s) roundtrip=%s %.0fs" % (
            camp, src_files, arc_files, src_bytes, tar_bytes, zst_bytes, entry["ratio"], roundtrip_ok, entry["seconds"]), flush=True)
    man = {"generated_at": datetime.now(timezone.utc).isoformat(), "repo": REPO, "release_tag": TAG,
           "compression": "zstandard level 12, python zstandard %s" % zstd.__version__,
           "captures": entries}
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    write_docs(man)
    print("wrote", MANIFEST)


def mb(n):
    return "%.1f" % (n / 1e6)


def table(caps):
    rows = ["| label | asset | campaign | source files | archived files | tar MB | zst MB | ratio | dropped sidecars |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in caps:
        rows.append("| %s | `%s` | `%s` | %d | %d | %s | %s | x%s | %d (%s MB) |" % (
            c["label"], c["asset_name"], c["campaign"], c["source_files"], c["archived_files"],
            mb(c["tar_bytes"]), mb(c["zst_bytes"]), c["ratio"], c["dropped_sidecars"]["count"],
            mb(c["dropped_sidecars"]["bytes"])))
    return "\n".join(rows)


def notes_for(man):
    caps = man["captures"]
    lines = ["# " + TITLE, "",
             "Disk-only pair receipts of the SCBench Codex/Cymatix paired regression-resistance A/B harness "
             "(Cymatix-Context branch `%s`, worktree head `%s`). These paths are gitignored on the branch "
             "and existed in no git ref; the committed part of the campaigns (manifests, READMEs, "
             "qualification receipts, Luna analysis) is mirrored under `mirror-branches/codex__scbench-cymatix-ab/`."
             % (SRC_BRANCH, caps[0]["source_head"][:12]), "",
             "Each asset is a tar (entries rooted at `benchmarks/scbench/campaigns/<campaign>/`) compressed with "
             "zstandard level 12. Verify the download against `sha256_zst`, decompress with python `zstandard` "
             "(`ZstdDecompressor().copy_stream`), verify `sha256_tar`, then extract. Sidecar `cymatix.genome.db` "
             "files were WAL-checkpointed on the copy and their `-wal`/`-shm` sidecars dropped; per-db source and "
             "archived sha256 are in `captures/scbench/MANIFEST.json`.", "",
             table(caps), "", "## Verdicts", ""]
    for c in caps:
        lines.append("- `%s` (frozen tag `%s`): %s" % (c["campaign"], c["frozen_tag"], c["verdict"]))
    lines += ["", "## sha256", ""]
    for c in caps:
        lines.append("- `%s`  zst %s  tar %s" % (c["asset_name"], c["sha256_zst"], c["sha256_tar"]))
    lines += ["", "## Privacy", "", PRIVACY_NOTE]
    return "\n".join(lines) + "\n"


def write_docs(man):
    (CAPT / ("notes_" + TAG + ".md")).write_text(notes_for(man), encoding="utf-8")
    caps = man["captures"]
    parts = ["# SCBench campaign receipts", "",
             "Release assets holding the gitignored pair receipts of the two SCBench Codex/Cymatix A/B campaigns "
             "(Luna pilot 2026-08-08, Terra 2026-08-11). Source: worktree `%s` at `%s` (branch `%s`); "
             "no git ref anywhere held these files. `MANIFEST.json` carries sizes, both hashes, asset URLs and "
             "the per-sidecar checkpoint records; the release notes are in `notes_%s.md`."
             % (SRC_WT, caps[0]["source_head"][:12], SRC_BRANCH, TAG), "",
             "Release: https://github.com/%s/releases/tag/%s" % (REPO, TAG), "",
             table(caps), "",
             "## Restore", "", "```python",
             "import hashlib, tarfile, zstandard as zstd",
             "src, dst = 'scbench-terra-2026-08-11.tar.zst', 'scbench-terra-2026-08-11.tar'",
             "with open(src, 'rb') as fi, open(dst, 'wb') as fo:",
             "    zstd.ZstdDecompressor().copy_stream(fi, fo)",
             "print(hashlib.sha256(open(dst, 'rb').read()).hexdigest())  # compare with sha256_tar",
             "tarfile.open(dst).extractall('<checkout of codex/scbench-cymatix-ab>', filter='data')",
             "```", "",
             "## Privacy", "", PRIVACY_NOTE, "",
             "Generated %s by `scripts/salvage_scbench.py`." % man["generated_at"]]
    (CAPT / "README.md").write_text("\n".join(parts) + "\n", encoding="utf-8")


def publish():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    caps = man["captures"]
    files = [str(OUT / c["asset_name"]) for c in caps]
    notes = CAPT / ("notes_" + TAG + ".md")
    exists = run(["gh", "release", "view", TAG, "--repo", REPO, "--json", "tagName"], check=False).returncode == 0
    if not exists:
        print("creating release " + TAG + " with " + str(len(files)) + " assets", flush=True)
        run(["gh", "release", "create", TAG, "--repo", REPO, "--title", TITLE,
             "--notes-file", str(notes)] + files, capture=False)
    else:
        print("release " + TAG + " exists; uploading missing/changed assets", flush=True)
        run(["gh", "release", "upload", TAG, "--repo", REPO, "--clobber"] + files, capture=False)
    assets = {}
    for attempt in range(3):
        r = run(["gh", "release", "view", TAG, "--repo", REPO, "--json", "assets"])
        assets = {a["name"]: a for a in json.loads(r.stdout)["assets"]}
        missing = [c for c in caps if c["asset_name"] not in assets or assets[c["asset_name"]]["size"] != c["zst_bytes"]]
        if not missing:
            break
        print("  retrying " + ", ".join(c["asset_name"] for c in missing), flush=True)
        run(["gh", "release", "upload", TAG, "--repo", REPO, "--clobber"]
            + [str(OUT / c["asset_name"]) for c in missing], capture=False)
    for c in caps:
        a = assets.get(c["asset_name"])
        c["asset_url"] = a["url"] if a else None
        c["asset_size_verified"] = bool(a and a["size"] == c["zst_bytes"])
        print("  %s %s %s %s" % ("OK " if c["asset_size_verified"] else "BAD", c["asset_name"],
                                 a["size"] if a else "-", c["asset_url"]), flush=True)
    man["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    write_docs(man)
    bad = [c["asset_name"] for c in caps if not c.get("asset_size_verified")]
    print("DONE; unverified assets: " + (", ".join(bad) if bad else "none"))


if __name__ == "__main__":
    {"build": build, "publish": publish, "docs": docs}[sys.argv[1]]()
