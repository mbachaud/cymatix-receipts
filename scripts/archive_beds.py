"""archive_beds.py -- compress curated knowledge-store snapshots to .db.zst + manifest.

Sources are NEVER modified: each .db (+ -wal if present) is copied to work/,
consolidated on the COPY, `VACUUM INTO` a compact single file under out/,
compressed with zstandard, round-trip verified, and the raw copies deleted.
Resumable: a bed whose .zst exists with a manifest entry is skipped.
"""
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import zstandard as zstd

sys.stdout.reconfigure(encoding="utf-8")

STAGING = Path("F:/Projects/cymatix-receipts-staging")
WORK, OUT, BEDS = STAGING / "work", STAGING / "out", STAGING / "beds"
MANIFEST = BEDS / "MANIFEST.json"
for d in (WORK, OUT, BEDS):
    d.mkdir(parents=True, exist_ok=True)

TAG_A, TAG_B = "early-beds-2026-04", "bench-beds-2026-05-to-07"
BLOBS = "E:/Helix-backup blobs"
BED_LIST = [
    ("helix-cache-genome", "A", TAG_A, "E:/helix-cache/genome.db"),
    ("genome-bench-2026-04-10", "A", TAG_A, BLOBS + "/genome-bench-2026-04-10.db"),
    ("genome-bench-2026-04-14", "A", TAG_A, BLOBS + "/genome-bench-2026-04-14.db"),
    ("genome-2026-04-15", "A", TAG_A, BLOBS + "/genome.db"),
    ("genomes-main-2026-04-21", "A", TAG_A, BLOBS + "/helix-context-2026-04-21/genomes-main-genome.db"),
    ("genome-bench-organic", "A", TAG_A, BLOBS + "/helix-context-2026-04-21/genome_bench_organic.db"),
    ("genome-cpu", "A", TAG_A, BLOBS + "/helix-context-2026-04-21/genome_cpu.db"),
    ("genome-llm-backup", "A", TAG_A, BLOBS + "/helix-context-2026-04-21/genome_llm_backup.db"),
    ("genome-bench-helix", "A", TAG_A, BLOBS + "/helix-context-2026-04-21/genome_bench_helix.db"),
    ("genome-bench-2026-05-08-frozen", "B", TAG_B, "F:/Projects/cymatix-context/benchmarks/genome-bench-2026-05-08-frozen.db"),
    ("bench-matrix-small", "B", TAG_B, "F:/Projects/helix-context/genomes/bench/matrix/small.db"),
    ("enterprise-rag-smoke", "B", TAG_B, "F:/Projects/helix-context/genomes/bench/enterprise_rag_smoke.db"),
    ("genomes-main-current", "B", TAG_B, "F:/Projects/cymatix-context/genomes/main/genome.db"),
    ("dogfood-bed", "B", TAG_B, "F:/Projects/cymatix-context/genomes/dogfood/genome.db"),
    ("assetops-bed", "B", TAG_B, "F:/Projects/cymatix-context/genomes/assetops-bed/genome.db"),
    ("taggerdogfood-e2b", "B", TAG_B, "F:/Projects/cymatix-context/genomes/taggerdogfood/genome.db"),
    ("taggerdogfood-cpu", "B", TAG_B, "F:/Projects/cymatix-context/genomes/taggerdogfood_cpu/genome.db"),
]
NOT_ARCHIVED = [
    "E:/Helix-backup blobs/genome-bench-2026-04-10.db.SAFETY_COPY (byte-duplicate of genome-bench-2026-04-10)",
    "E:/Helix-backup blobs/genome-bench-{A3,fresh,N1000,N50,PKI,PKI2}.db (mid-experiment variants of the 2026-04-12/13 bench bed)",
    "E:/Helix-backup blobs/helix-context-2026-04-21/genome.db (+wal) and genome_2026-04-15_pre_fresh.db (near-duplicates of genome-2026-04-15)",
    "E:/Helix-backup blobs/helix-context-2026-04-21/genome.db.pre-*.bak (pre-compact / pre-backfill / pre-reingest safety copies)",
    "F:/Projects/helix-context/genomes/bench/{matrix,sike_beds}/* larger than 500 MB (matrix medium/large/xl, enterprise_rag_10k/50k, sike beds): live bench beds, 165 GB, stay in place",
]
PRIVACY_TYPES = ("exchange", "conversation", "chat", "turn", "query_response",
                 "chat_exchange", "qa_exchange", "proxy_exchange")
PRIVACY_TABLES = {"exchanges", "sessions", "turns", "conversations",
                  "session_deliveries", "hitl_events"}


def sha256_path(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def top10(con, table, col):
    try:
        rows = con.execute(
            "SELECT " + col + ", COUNT(*) c FROM " + table + " GROUP BY " + col
            + " ORDER BY c DESC LIMIT 10").fetchall()
        return [{"value": (str(v)[:80] if v is not None else None), "count": c}
                for v, c in rows]
    except Exception as exc:
        return [{"error": type(exc).__name__}]


def iso(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 1e9:
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
        except Exception:
            return str(v)
    return str(v)[:40]


def gather_meta(con):
    m = {}
    m["page_size"] = con.execute("PRAGMA page_size").fetchone()[0]
    m["page_count"] = con.execute("PRAGMA page_count").fetchone()[0]
    m["user_version"] = con.execute("PRAGMA user_version").fetchone()[0]
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    m["tables"] = tables
    m["doc_count"] = None
    m["date_range"] = None
    m["content_types"] = None
    m["sources"] = None
    cols = []
    if "genes" in tables:
        cols = [r[1] for r in con.execute("PRAGMA table_info(genes)")]
        m["doc_count"] = con.execute("SELECT COUNT(*) FROM genes").fetchone()[0]
        for c in ("created_at", "ingested_at", "updated_at", "timestamp", "created"):
            if c in cols:
                mn, mx = con.execute(
                    "SELECT MIN(" + c + "), MAX(" + c + ") FROM genes").fetchone()
                m["date_range"] = {"column": "genes." + c, "min": iso(mn), "max": iso(mx)}
                break
        if m["date_range"] is None and "epigenetics" in tables:
            ecols = [r[1] for r in con.execute("PRAGMA table_info(epigenetics)")]
            for c in ("created_at", "last_accessed", "updated_at"):
                if c in ecols:
                    mn, mx = con.execute(
                        "SELECT MIN(" + c + "), MAX(" + c + ") FROM epigenetics").fetchone()
                    m["date_range"] = {"column": "epigenetics." + c, "min": iso(mn), "max": iso(mx)}
                    break
        if "content_type" in cols:
            m["content_types"] = top10(con, "genes", "content_type")
        for c in ("source", "domain", "origin", "source_id"):
            if c in cols:
                m["sources"] = {"column": c, "top10": top10(con, "genes", c)}
                break
    # privacy heuristic: counts only, never content
    priv = {
        "heuristic": ("genes.content_type in exchange/conversation/chat/turn/"
                      "query_response set; genes.source|origin|domain LIKE "
                      "%exchange%|%proxy%|%chat%; row counts of tables named "
                      "exchanges/sessions/turns/conversations/session_deliveries/hitl_events"),
        "count": 0, "detail": {}}
    if "genes" in tables:
        if "content_type" in cols:
            q = ",".join("?" * len(PRIVACY_TYPES))
            n = con.execute(
                "SELECT COUNT(*) FROM genes WHERE lower(content_type) IN (" + q + ")",
                PRIVACY_TYPES).fetchone()[0]
            priv["detail"]["genes.content_type"] = n
            priv["count"] += n
        for c in ("source", "origin", "domain"):
            if c in cols:
                n = con.execute(
                    "SELECT COUNT(*) FROM genes WHERE lower(" + c + ") LIKE '%exchange%'"
                    " OR lower(" + c + ") LIKE '%proxy%' OR lower(" + c + ") LIKE '%chat%'"
                ).fetchone()[0]
                priv["detail"]["genes." + c] = n
                priv["count"] += n
    for t in tables:
        if t.lower() in PRIVACY_TABLES:
            n = con.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
            priv["detail"]["table:" + t] = n
            priv["count"] += n
    m["privacy_flag"] = priv
    return m


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"generated_at": None, "repo": "mbachaud/cymatix-receipts",
            "beds": [], "not_archived": NOT_ARCHIVED}


def save_manifest(man):
    man["generated_at"] = datetime.now(timezone.utc).isoformat()
    man["not_archived"] = NOT_ARCHIVED
    MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")


def archive_one(label, group, tag, src):
    src = Path(src)
    zpath = OUT / (label + ".db.zst")
    entry = {
        "label": label, "group": group, "release_tag": tag, "asset_name": zpath.name,
        "source_path": str(src),
        "source_mtime": datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).isoformat(),
        "source_bytes": src.stat().st_size, "asset_url": None, "notes": []}
    wal = src.with_name(src.name + "-wal")
    has_wal = wal.exists() and wal.stat().st_size > 0
    if has_wal:
        entry["source_wal_bytes"] = wal.stat().st_size
    t0 = time.time()
    wdir = WORK / label
    if wdir.exists():
        shutil.rmtree(wdir)
    wdir.mkdir(parents=True)
    wdb = wdir / "copy.db"
    shutil.copyfile(src, wdb)
    if has_wal:
        shutil.copyfile(wal, wdir / "copy.db-wal")
        entry["notes"].append("WAL copied alongside and checkpointed on the copy")
    raw = OUT / (label + ".db")
    if raw.exists():
        raw.unlink()
    con = sqlite3.connect(str(wdb))
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("PRAGMA journal_mode=DELETE")
        entry["quick_check"] = con.execute("PRAGMA quick_check").fetchone()[0]
        entry.update(gather_meta(con))
        con.execute("VACUUM INTO ?", (str(raw).replace("\\", "/"),))
    finally:
        con.close()
    entry["vacuumed_bytes"] = raw.stat().st_size
    entry["sha256_raw"] = sha256_path(raw)
    cctx = zstd.ZstdCompressor(level=12, threads=-1)
    with open(raw, "rb") as fi, open(zpath, "wb") as fo:
        cctx.copy_stream(fi, fo, size=raw.stat().st_size)
    entry["zst_bytes"] = zpath.stat().st_size
    entry["sha256_zst"] = sha256_path(zpath)
    entry["ratio"] = round(entry["vacuumed_bytes"] / max(1, entry["zst_bytes"]), 2)
    h = hashlib.sha256()
    dctx = zstd.ZstdDecompressor()
    with open(zpath, "rb") as fz:
        with dctx.stream_reader(fz) as rd:
            for chunk in iter(lambda: rd.read(1 << 20), b""):
                h.update(chunk)
    entry["roundtrip_ok"] = (h.hexdigest() == entry["sha256_raw"])
    if not entry["roundtrip_ok"]:
        raise RuntimeError(label + ": round-trip sha mismatch")
    raw.unlink()
    shutil.rmtree(wdir, ignore_errors=True)
    entry["seconds"] = round(time.time() - t0, 1)
    return entry


def main():
    man = load_manifest()
    done = {b["label"] for b in man["beds"] if b.get("sha256_zst")}
    for label, group, tag, src in BED_LIST:
        if label in done and (OUT / (label + ".db.zst")).exists():
            print("skip " + label + " (done)", flush=True)
            continue
        man["beds"] = [b for b in man["beds"] if b["label"] != label]
        if not Path(src).exists():
            print("MISSING " + label + ": " + src, flush=True)
            man["beds"].append({"label": label, "group": group, "release_tag": tag,
                                "source_path": src, "error": "source missing"})
            save_manifest(man)
            continue
        print("archiving " + label + " <- " + src, flush=True)
        try:
            e = archive_one(label, group, tag, src)
        except Exception as exc:
            print("FAILED " + label + ": " + type(exc).__name__ + ": " + str(exc), flush=True)
            man["beds"].append({"label": label, "group": group, "release_tag": tag,
                                "source_path": src,
                                "error": type(exc).__name__ + ": " + str(exc)})
            save_manifest(man)
            continue
        man["beds"].append(e)
        save_manifest(man)
        print("  ok %s: raw %.1f MB -> zst %.1f MB (x%s), docs=%s privacy=%s %ss" % (
            label, e["vacuumed_bytes"] / 1e6, e["zst_bytes"] / 1e6, e["ratio"],
            e["doc_count"], e["privacy_flag"]["count"], e["seconds"]), flush=True)
    order = {l: i for i, (l, _g, _t, _s) in enumerate(BED_LIST)}
    man["beds"].sort(key=lambda b: order.get(b["label"], 999))
    save_manifest(man)
    print("manifest -> " + str(MANIFEST))


if __name__ == "__main__":
    main()
