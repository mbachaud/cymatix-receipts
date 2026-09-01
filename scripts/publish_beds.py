"""publish_beds.py -- upload archived beds as GitHub Release assets and backfill the manifest.

Idempotent: creates a release per tag if missing, uploads (or re-uploads with
--clobber) every asset in that group, verifies remote sizes, writes asset URLs
into beds/MANIFEST.json, and renders beds/README.md.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STAGING = Path("F:/Projects/cymatix-receipts-staging")
OUT, BEDS = STAGING / "out", STAGING / "beds"
MANIFEST = BEDS / "MANIFEST.json"
REPO = "mbachaud/cymatix-receipts"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TITLES = {
    "early-beds-2026-04": "Early knowledge-store snapshots (Helix era, April 2026)",
    "bench-beds-2026-05-to-07": "Bench and dogfood beds (May to July 2026)",
}
PRIVACY_NOTE = (
    "Privacy audit: a name-based heuristic (content_type / source / origin columns, "
    "exchange-like table names) found no persisted query/response exchanges; the only "
    "flagged rows are hitl_events records (human-in-the-loop pause events, counts in the "
    "manifest). These schemas carry no content_type column, so the audit is not a content "
    "scan. The repository stays private until an owner review clears it."
)


def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True, creationflags=NOWIN,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("cmd failed (%s): %s\n%s" % (r.returncode, " ".join(cmd), r.stderr))
    return r


def mb(n):
    return "%.1f" % (n / 1e6)


def table(beds):
    rows = ["| label | asset | raw MB | zst MB | ratio | docs | privacy rows | source |",
            "|---|---|---:|---:|---:|---:|---:|---|"]
    for b in beds:
        rows.append("| %s | `%s` | %s | %s | x%s | %s | %s | `%s` |" % (
            b["label"], b["asset_name"], mb(b["vacuumed_bytes"]), mb(b["zst_bytes"]),
            b["ratio"], b["doc_count"], b["privacy_flag"]["count"], b["source_path"]))
    return "\n".join(rows)


def notes_for(tag, beds):
    lines = ["# " + TITLES[tag], "",
             "Compressed SQLite knowledge stores (`VACUUM INTO` copies of the originals, "
             "zstandard level 12). Verify each download against `sha256_zst` in "
             "`beds/MANIFEST.json`, then decompress with python `zstandard` "
             "(`ZstdDecompressor().copy_stream`) and verify `sha256_raw`.", "",
             table(beds), "", "## sha256 (zst)", ""]
    for b in beds:
        lines.append("- `%s`  %s" % (b["asset_name"], b["sha256_zst"]))
    lines += ["", "## Privacy", "", PRIVACY_NOTE]
    return "\n".join(lines) + "\n"


def readme(man):
    ok = [b for b in man["beds"] if "error" not in b]
    parts = ["# Archived beds", "",
             "Knowledge-store snapshots archived as GitHub Release assets of this repository. "
             "Each asset is a `VACUUM INTO` copy of the source database (WAL checkpointed on the "
             "copy, sources never modified), compressed with zstandard level 12 and round-trip "
             "verified. `MANIFEST.json` carries both hashes, row counts, table lists, and the "
             "privacy heuristic result per bed.", ""]
    for tag in TITLES:
        grp = [b for b in ok if b["release_tag"] == tag]
        parts += ["## Release `%s`: %s" % (tag, TITLES[tag]), "",
                  "https://github.com/%s/releases/tag/%s" % (REPO, tag), "", table(grp), ""]
    parts += ["## Restore", "", "```python",
              "import hashlib, zstandard as zstd",
              "src, dst = 'dogfood-bed.db.zst', 'dogfood-bed.db'",
              "with open(src, 'rb') as fi, open(dst, 'wb') as fo:",
              "    zstd.ZstdDecompressor().copy_stream(fi, fo)",
              "print(hashlib.sha256(open(dst, 'rb').read()).hexdigest())  # compare with sha256_raw",
              "```", "",
              "## Not archived", ""]
    parts += ["- " + n for n in man.get("not_archived", [])]
    parts += ["", "## Privacy", "", PRIVACY_NOTE, "",
              "Generated %s by `publish_beds.py`." % datetime.now(timezone.utc).isoformat()]
    return "\n".join(parts) + "\n"


def main():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ok = [b for b in man["beds"] if "error" not in b]
    for tag in TITLES:
        grp = [b for b in ok if b["release_tag"] == tag]
        files = [str(OUT / b["asset_name"]) for b in grp]
        notes = BEDS / ("notes_" + tag + ".md")
        notes.write_text(notes_for(tag, grp), encoding="utf-8")
        exists = run(["gh", "release", "view", tag, "--repo", REPO, "--json", "tagName"],
                     check=False).returncode == 0
        if not exists:
            print("creating release " + tag + " with " + str(len(files)) + " assets", flush=True)
            run(["gh", "release", "create", tag, "--repo", REPO, "--title", TITLES[tag],
                 "--notes-file", str(notes)] + files, capture=False)
        else:
            print("release " + tag + " exists; uploading missing/changed assets", flush=True)
            run(["gh", "release", "upload", tag, "--repo", REPO, "--clobber"] + files, capture=False)
        # verify + backfill
        for attempt in range(3):
            r = run(["gh", "release", "view", tag, "--repo", REPO, "--json", "assets"])
            assets = {a["name"]: a for a in json.loads(r.stdout)["assets"]}
            missing = [b for b in grp if b["asset_name"] not in assets
                       or assets[b["asset_name"]]["size"] != b["zst_bytes"]]
            if not missing:
                break
            print("  retrying " + str(len(missing)) + " asset(s): "
                  + ", ".join(b["asset_name"] for b in missing), flush=True)
            run(["gh", "release", "upload", tag, "--repo", REPO, "--clobber"]
                + [str(OUT / b["asset_name"]) for b in missing], capture=False)
        for b in grp:
            a = assets.get(b["asset_name"])
            b["asset_url"] = a["url"] if a else None
            b["asset_size_verified"] = bool(a and a["size"] == b["zst_bytes"])
            print("  %s %s %s" % ("OK " if b["asset_size_verified"] else "BAD", b["asset_name"],
                                  b["asset_url"]), flush=True)
    man["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")
    (BEDS / "README.md").write_text(readme(man), encoding="utf-8")
    bad = [b["asset_name"] for b in ok if not b.get("asset_size_verified")]
    print("DONE; unverified assets: " + (", ".join(bad) if bad else "none"))


if __name__ == "__main__":
    main()
