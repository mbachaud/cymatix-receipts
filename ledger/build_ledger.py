#!/usr/bin/env python
"""Build ledger/ledger.json from the receipts already on disk in this clone.

Stdlib only. Run from the clone root:

    python ledger/build_ledger.py

Re-running regenerates ledger/ledger.json byte-for-byte except `generated_at`.

Design rules (these are enforced, not aspirational):

* Every number written into the ledger is copied out of a receipt file or out of
  a named row of `mirror/docs/benchmarks/BASELINES.md`. Nothing is computed from
  memory, and nothing is derived by arithmetic that the source did not already
  perform. When a receipt carries a count but not a rate, the count goes into
  `notes` and the rate field stays null.
* `delivered_gold_rate` (post-budget delivery slice) and `final_recall_at_12`
  (final ranked order) are different metrics and never merged. `recall_at_12` is
  the candidate-pool / score-map basis.
* Paths in `receipt` are relative to the clone root, so mirrored receipts start
  with `mirror/`. BASELINES.md cites the same files without that prefix.
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import glob
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "ledger", "ledger.json")
SOURCE_COMMIT = "2644c3e44038bf285eb6a5484817bd4c3de126c6"

BASELINES = "mirror/docs/benchmarks/BASELINES.md"
ERB_DIR = "mirror/benchmarks/dogfood/erb/receipts"
DOGFOOD_RECEIPTS = "mirror/benchmarks/dogfood/receipts"
DATA_DIR = "mirror/docs/benchmarks/data"
RESEARCH_DIR = "mirror/docs/research/data"
SNOW_DIR = "mirror/benchmarks/snow/results"


# ---------------------------------------------------------------- utilities


def rp(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p)


def load(relpath: str):
    with open(os.path.join(ROOT, relpath), "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_text(relpath: str) -> str:
    with open(os.path.join(ROOT, relpath), "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def ls(reldir: str, pattern: str = "*.json") -> list[str]:
    hits = glob.glob(os.path.join(ROOT, reldir, pattern))
    return sorted(rp(reldir, os.path.basename(h)) for h in hits)


def slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return out or "x"


DATE_RE = re.compile(r"(20\d\d)-(\d\d)-(\d\d)")
COMPACT_RE = re.compile(r"^(20\d\d)(\d\d)(\d\d)")


def derive_date(basename: str, doc: dict) -> str | None:
    """Date of the run: filename date, then stamp, then measured_at/generated_at."""
    m = DATE_RE.search(basename)
    if m:
        return "-".join(m.groups())
    for key in ("stamp", "measured_at", "generated_at", "timestamp"):
        val = doc.get(key) if isinstance(doc, dict) else None
        if not isinstance(val, str):
            continue
        m = DATE_RE.search(val)
        if m:
            return "-".join(m.groups())
        m = COMPACT_RE.match(val)
        if m:
            return "-".join(m.groups())
    return None


def num(val):
    """Receipt fields are sometimes stringified. Keep numbers, drop everything else."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        try:
            return int(val) if re.fullmatch(r"-?\d+", val) else float(val)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- bed identity

BED_BY_PATH = {
    "f:/tmp/erb_carve/erb_10k.db": "erb_10k",
    "f:/tmp/erb_carve/erb_100k.db": "erb_100k",
    "f:/tmp/erb_carve/erb_250k.db": "erb_250k",
    "f:/tmp/erb_carve/erb_500k.db": "erb_500k",
    "f:/tmp/erb_carve/erb_829k_nosplade.db": "erb_829k_nosplade",
    "f:/tmp/erb_blob.db": "erb_blob_829k",
    "f:/tmp/erb_blob_probe.db": "erb_blob_probe",
    "f:/tmp/erb_blob_v09x.db": "erb_blob_v09x_947k",
    "f:/projects/cymatix-context/genomes/dogfood/genome.db": "dogfood",
    "f:/projects/cymatix-context/genomes/taggerdogfood/genome.db": "taggerdogfood_e2b",
    "f:/projects/cymatix-context/genomes/taggerdogfood_cpu/genome.db": "taggerdogfood_cpu",
    "f:/projects/cymatix-context/genomes/_ftsarms/fts_none.db": "dogfood_ftsarm_none",
    "f:/projects/cymatix-context/genomes/_ftsarms/fts_cap02.db": "dogfood_ftsarm_cap02",
    "f:/projects/cymatix-context/genomes/_ftsarms/clean_fts_cap02.db": "dogfood_clean_ftsarm_cap02",
    "f:/tmp/sike-bed-pointers/stage/enterprise_rag_10k.db": "enterprise_rag_10k",
    "f:/tmp/sike-bed-pointers/stage/enterprise_rag_50k.db": "enterprise_rag_50k",
    "genomes/bench/matrix/xl.db": "sike_xl",
    "xl": "sike_xl",
    "xl_clean": "sike_xl_clean",
    "enterprise_rag_10k": "enterprise_rag_10k",
    "enterprise_rag_50k": "enterprise_rag_50k",
    "genome": "snow_genome",
}

# The dogfood bed was re-cut on 2026-07-29 (155 genes dropped); the two states
# have different identity digests, so they are different beds.
DOGFOOD_CLEAN_FROM = "2026-07-29"


def bed_id_for(raw, date: str | None) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    key = raw.replace("\\", "/").lower()
    bid = BED_BY_PATH.get(key)
    if bid is None:
        return None
    if bid == "dogfood" and date and date >= DOGFOOD_CLEAN_FROM:
        return "dogfood_clean"
    return bid


BEDS = [
    {
        "id": "erb_10k",
        "family": "erb",
        "genes": None,
        "size_bytes": 704892928,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": (
            "EnterpriseRAG-Bench carve. size_bytes = bed_bytes in "
            "mirror/benchmarks/dogfood/erb/receipts/splade_ab_10k.json. tagger_version=1 by the "
            "BASELINES.md tagger-version rule (every bed built before 2026-08-30 is v1)."
        ),
    },
    {
        "id": "erb_100k",
        "family": "erb",
        "genes": 100000,
        "size_bytes": 6448840704,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": (
            "genes = bed_control_tag_scan.gene_count in "
            "mirror/benchmarks/dogfood/erb/receipts/neutralize_ab_100k.json. size_bytes = bed_bytes "
            "in enc_iso_100k_run1_fwd.json; receipts across the year record 6,426,775,552 to "
            "6,448,865,280 bytes for this file (health_log growth). 141-needle full carve set."
        ),
    },
    {
        "id": "erb_250k",
        "family": "erb",
        "genes": None,
        "size_bytes": 15826972672,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "size_bytes = bed_bytes in enc_iso_250k_run1_fwd.json. Carve line shares one resolved needle set.",
    },
    {
        "id": "erb_500k",
        "family": "erb",
        "genes": None,
        "size_bytes": 31249076224,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "size_bytes = bed_bytes in enc_iso_500k_run1_fwd.json.",
    },
    {
        "id": "erb_blob_829k",
        "family": "erb",
        "genes": None,
        "size_bytes": 56723681280,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": (
            "The 829k ERB blob, blob-resolved needle set (n=469 full, n=30 probe) - NOT "
            "needle-comparable with the carve line (2026-08-14-encoder-isolation-scale-curve.md). "
            "size_bytes = bed_bytes in enc_iso_829k_run1_fwd.json (pre-ops). BASELINES.md "
            "bed-state note: rebuilt by 2026-08-20 maintenance (PKI drop + FTS5 external-content "
            "migration + vacuum) to 37,055,066,112 bytes; bed-bytes from daggered rows are not "
            "comparable to post-ops measurements."
        ),
    },
    {
        "id": "erb_blob_probe",
        "family": "erb",
        "genes": None,
        "size_bytes": 56724590592,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "Probe copy of the 829k blob used by the rerank A/B receipts. size_bytes = smallest bed_bytes recorded for it.",
    },
    {
        "id": "erb_829k_nosplade",
        "family": "erb",
        "genes": None,
        "size_bytes": 34391937024,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": (
            "829k blob rebuilt without the SPLADE expansion index. size_bytes = bed_bytes in "
            "enc_iso_829k_nosplade_run1.json (pre-ops). BASELINES.md bed-state note gives the "
            "post-2026-08-20-ops size as 17,433,264,128 bytes."
        ),
    },
    {
        "id": "erb_blob_v09x_947k",
        "family": "erb",
        "genes": 947531,
        "size_bytes": 24339210240,
        "tagger_version": 1,
        "ingest_c": 6,
        "identity": "11a05b91...",
        "notes": (
            "BASELINES.md row 2026-08-27-ranking-under-width-wave1: 947,531 genes, 24,339,210,240 "
            "bytes, provenance-stamped build 2026-08-26 at 5f5c677+dirty, cpu tagger, ingest_c=6, "
            "identity 11a05b91..., builder scripts/build_erb_blob_v09x.py. Receipts record "
            "bed_bytes 24,338,374,656 to 24,571,052,032 for the same file, so the BASELINES figure "
            "is the build-time size and the receipts are run-time sizes - recorded as a "
            "disagreement, not reconciled. Needle set v09x n=470 (half-set n=235)."
        ),
    },
    {
        "id": "dogfood",
        "family": "dogfood",
        "genes": 6427,
        "size_bytes": 267567104,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": "eb2c7403176ce36c378b30cba384e6f3663b17607ef373a049363c49beae10df",
        "notes": (
            "Pre-clean dogfood bed. genes/identity from "
            "mirror/docs/benchmarks/data/2026-07-28-dogfood-gene-id-summary.json (genes_total 6427, "
            "gold_genes 471). size_bytes = smallest bed_bytes recorded against this path."
        ),
    },
    {
        "id": "dogfood_clean",
        "family": "dogfood",
        "genes": 6272,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": "13f8bbe3d3a37912d7686eef6fdf61a2d2cb6a584eed98863d57ddc8a2262ddd",
        "notes": (
            "Dogfood bed after the 2026-07-29 clean re-cut. genes/identity from "
            "2026-07-29-dogfood-gene-id-summary-clean.json (genes_total 6272, gold_genes 421). "
            "Same file path as bed dogfood, different content digest, so measurements before and "
            "after 2026-07-29 are not comparable."
        ),
    },
    {
        "id": "dogfood_sema_ab",
        "family": "dogfood",
        "genes": 6788,
        "size_bytes": 108003328,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": "b1951b8d7cffb0e56394df16da94c0005fd3334c6d78099e6449827fd5516e95",
        "notes": (
            "Purpose-built pair for the 2026-08-19 sema ingest A/B "
            "(mirror/benchmarks/dogfood/receipts/sema_ingest_ab_dogfood.json). Both arms have the "
            "IDENTICAL gene-id identity digest (content-derived ids prove corpus equivalence); the "
            "beds differ only in the embedding column. size_bytes is arm A (108,003,328); arm B is "
            "107,487,232. Corpus snapshot digest 104c01a4..., 18 needles."
        ),
    },
    {
        "id": "taggerdogfood_e2b",
        "family": "dogfood",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": "60d88fb324322b2e9123",
        "notes": (
            "Dogfood corpus ingested with the gemma4:e2b LLM tagger. identity = "
            "bed_identity_sha256 prefix recorded in 2026-07-31-expression-arms-taggerbed.json "
            "(truncated there). Campaign 2026-07-31-tagger-ab-tag-flood."
        ),
    },
    {
        "id": "taggerdogfood_cpu",
        "family": "dogfood",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "Dogfood corpus ingested with the CPU tagger; comparator for taggerdogfood_e2b.",
    },
    {
        "id": "dogfood_ftsarm_none",
        "family": "dogfood",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "FTS-arm variant bed for the 2026-07-31 tag-flood campaign (no FTS tag cap).",
    },
    {
        "id": "dogfood_ftsarm_cap02",
        "family": "dogfood",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "FTS-arm variant bed for the 2026-07-31 tag-flood campaign (cap 0.2).",
    },
    {
        "id": "dogfood_clean_ftsarm_cap02",
        "family": "dogfood",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "Clean-bed FTS-arm variant for the 2026-07-31 tag-flood campaign.",
    },
    {
        "id": "enronqa_native",
        "family": "enronqa",
        "genes": 84665,
        "size_bytes": 1169428480,
        "tagger_version": 1,
        "ingest_c": 1,
        "identity": None,
        "notes": (
            "BASELINES.md row 2026-08-29-enronqa-native-baseline: F:/tmp/enronqa_bed/enronqa.db, "
            "84,665 genes, 1,169,428,480 bytes, sequential ingest_c=1, built 2026-08-29 from the "
            "73,772-email EnronQA corpus (hf:MichaelR207/enron_qa_0922, CC BY 4.0). NEW CORPUS - "
            "the row states it is not comparable to any ERB row. Needle set = 250 pairs "
            "(500 needles, original/rephrased with identical gold per pair)."
        ),
    },
    {
        "id": "enronqa_v2",
        "family": "enronqa",
        "genes": 84677,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": 1,
        "identity": "158fa8a3ae3ee17c... (gene-id-set sha256, sorted gene_ids newline-joined)",
        "notes": "BASELINES.md row 2026-08-30-v091-gate-sweep: F:/tmp/enronqa_bed_v2/enronqa.db, 84,677 genes, ingest_c=1, tagger_v1.",
    },
    {
        "id": "enronqa_v2c",
        "family": "enronqa",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": 1,
        "identity": "158fa8a3ae3ee17c... (identical to enronqa_v2)",
        "notes": (
            "BASELINES.md row 2026-08-30-entity-hub-cutoff-retrieval-ab: paired with enronqa_v2, "
            "differing ONLY in entity_autolink_hub_cutoff (0 vs 200). Gene-id-set digests are "
            "IDENTICAL, so the beds are content-equal and only relation=5 COVER edges differ."
        ),
    },
    {
        "id": "enronqa_padded",
        "family": "enronqa",
        "genes": 596707,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": 6,
        "identity": "a537e2413f624d10... (gene-id-set sha256)",
        "notes": (
            "BASELINES.md row 2026-08-30-v091-gate-sweep: F:/tmp/enronqa_padded_bed/enronqa_padded.db, "
            "596,707 genes / 517,353 files, ingest_c=6, entity_autolink_hub_cutoff=200, built in "
            "4h58m. Parallel ingest was NOT blessed on this corpus (equivalence gate failed on "
            "gene_relations -0.13%); the user ruled a pragmatic exception on 2026-08-29."
        ),
    },
    {
        "id": "sike_xl",
        "family": "sike",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "SIKE matrix xl bed (genomes/bench/matrix/xl.db). Legacy helix-era bed; ingest concurrency not recorded, so not comparable across beds under the BASELINES ingest_c rule.",
    },
    {
        "id": "sike_xl_clean",
        "family": "sike",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "Cleaned variant of the SIKE xl bed used by the 2026-07-06 rebaseline and 2026-07-10 combinator receipts.",
    },
    {
        "id": "enterprise_rag_10k",
        "family": "sike",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "EnterpriseRAG 10k SIKE bed used by the 2026-07-11 bedsweep and the SPLADE curve receipts.",
    },
    {
        "id": "enterprise_rag_50k",
        "family": "sike",
        "genes": None,
        "size_bytes": None,
        "tagger_version": 1,
        "ingest_c": "unknown",
        "identity": None,
        "notes": "EnterpriseRAG 50k SIKE bed used by the 2026-07-11 bedsweep and the SPLADE curve receipts.",
    },
    {
        "id": "snow_genome",
        "family": "snow",
        "genes": 7807,
        "size_bytes": None,
        "tagger_version": None,
        "ingest_c": "unknown",
        "identity": None,
        "notes": (
            "April 2026 snow-harness bed. genes = meta.gene_count in "
            "mirror/benchmarks/snow/results/snow_oracle-only_2026-04-17.json (7,807; the "
            "2026-04-16 run records 7,807 as well). Pre-dates both the ingest_c and the "
            "tagger_version rules."
        ),
    },
    {
        "id": "muloc",
        "family": "muloc",
        "genes": None,
        "size_bytes": None,
        "tagger_version": None,
        "ingest_c": None,
        "identity": None,
        "notes": (
            "MULocBench bed. NOT present in this archive: no manifest entry, no receipt. Named "
            "only by research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md, which cites "
            "benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json (listed "
            "under `missing`). Every field here is null on purpose."
        ),
    },
    {
        "id": "locomo",
        "family": "locomo",
        "genes": None,
        "size_bytes": None,
        "tagger_version": None,
        "ingest_c": None,
        "identity": None,
        "notes": (
            "LoCoMo bed. NOT present in this archive. Named only by "
            "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md and "
            "2026-08-31-plan-red-team.md (semantic-portfolio-lane doc in worktree vigilant-wu-5416d6). "
            "No receipt mirrored; see `missing`."
        ),
    },
    {
        "id": "financebench",
        "family": "financebench",
        "genes": None,
        "size_bytes": None,
        "tagger_version": None,
        "ingest_c": None,
        "identity": None,
        "notes": (
            "FinanceBench bed. NOT present in this archive. Named only by "
            "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md "
            "('FinanceBench baseline blackout'). No receipt mirrored; see `missing`."
        ),
    },
]

KNOWN_BED_IDS = {b["id"] for b in BEDS}


# ---------------------------------------------------------------- BASELINES.md


def parse_baselines_rows() -> list[dict]:
    """Parse the campaign table of BASELINES.md into rows we can cite."""
    text = read_text(BASELINES)
    rows: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        name = cells[0]
        if name.lower() in ("campaign", "box") or set(name) <= set("-: "):
            continue
        name = name.replace("\u2020", "").strip()
        name = re.sub(r"`", "", name)
        if not re.match(r"^20\d\d-\d\d-\d\d", name) and "codex" not in name and "planned" not in name:
            continue
        if name in seen:
            continue
        seen.add(name)
        patterns = set()
        for tok in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_/.*{},-]*\.json", cells[7]):
            patterns.add(tok)
        rows.append(
            {
                "name": name,
                "commit_cell": cells[1],
                "status_cell": cells[6],
                "receipts_cell": cells[7],
                "patterns": sorted(patterns),
            }
        )
    return rows


def expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out = []
    for opt in m.group(1).split(","):
        out.extend(expand_braces(pattern[: m.start()] + opt + pattern[m.end() :]))
    return out


BASELINE_ROWS = parse_baselines_rows()

# Receipts that fall inside a broader row's glob but belong to their own arm.
# `ladder_v09x_*.json` in the wave-1 row would otherwise swallow the two W2 arms
# and the v0.9.1 integration confirm.
CAMPAIGN_OVERRIDE = {
    "ladder_v09x_w2_cover_walk_2026-08-28.json": (
        "2026-08-28-w2.1-cover-walk-arm",
        None,
        "Matches the wave-1 row's ladder_v09x_*.json glob but is a separate W2.1 arm; BASELINES has no row of its own for it.",
    ),
    "ladder_v09x_w24_min_delivered_2026-08-28.json": (
        "2026-08-28-w2.4-min-delivered-floor-arm",
        None,
        "Matches the wave-1 row's ladder_v09x_*.json glob but is a separate W2.4 arm; BASELINES has no row of its own for it.",
    ),
}


def campaign_for(basename: str, date: str | None) -> tuple[str, str | None, str | None]:
    """(campaign, baselines_row, extra_note) for a receipt basename."""
    if basename in CAMPAIGN_OVERRIDE:
        return CAMPAIGN_OVERRIDE[basename]
    best: tuple[int, str, str] | None = None
    for row in BASELINE_ROWS:
        for pat in row["patterns"]:
            for expanded in expand_braces(pat):
                tail = expanded.rsplit("/", 1)[-1]
                if fnmatch.fnmatch(basename, tail):
                    score = len(tail) - tail.count("*") * 8
                    if best is None or score > best[0]:
                        best = (score, row["name"], row["name"])
    if best is not None:
        return best[1], best[2], None
    stem = basename[:-5] if basename.endswith(".json") else basename
    stems = [stem]
    stripped = re.sub(r"^20\d\d-\d\d-\d\d[-_]", "", stem)
    if stripped != stem:
        stems.append(stripped)
    writeups = [
        os.path.basename(d)
        for d in sorted(ls("mirror/docs/benchmarks", "*.md"))
        if DATE_RE.match(os.path.basename(d))
    ]
    # 1. a dated write-up that names the receipt outright
    for wu in writeups:
        text = read_text(rp("mirror/docs/benchmarks", wu))
        if any(s in text for s in stems):
            return wu[:-3], None, "campaign taken from the write-up that names this receipt; no BASELINES row matches it"
    # 2. otherwise the dated write-up from the same day whose slug shares the most
    #    words with the receipt name, when that winner is unique
    if date:
        same_day = [w for w in writeups if w.startswith(date)]
        if len(same_day) == 1:
            return (
                same_day[0][:-3],
                None,
                "campaign attributed by date: the only write-up from this day, which does not name the receipt outright",
            )
        if same_day:
            toks = set(re.split(r"[^a-z0-9]+", stem.lower()))
            scored = sorted(
                ((len(toks & set(re.split(r"[^a-z0-9]+", w[11:-3].lower()))), w) for w in same_day),
                reverse=True,
            )
            if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                return (
                    scored[0][1][:-3],
                    None,
                    "campaign attributed by date and name overlap; the write-up does not name the receipt outright",
                )
    return "uncategorized", None, "no BASELINES row and no dated write-up names this receipt"


# ---------------------------------------------------------------- measurements

MEASUREMENTS: list[dict] = []
UNPARSED: list[dict] = []


def add(m: dict) -> None:
    for key in (
        "id",
        "date",
        "bed_id",
        "campaign",
        "arm",
        "n",
        "delivered_gold_rate",
        "recall_at_12",
        "final_recall_at_12",
        "median_gold_rank",
        "basis",
        "shipped_default",
        "receipt",
        "baselines_row",
        "pr",
        "git_sha",
        "notes",
    ):
        m.setdefault(key, None)
    if m["bed_id"] is not None and m["bed_id"] not in KNOWN_BED_IDS:
        raise SystemExit("unknown bed id: %r (%s)" % (m["bed_id"], m["id"]))
    MEASUREMENTS.append(m)


def arm_metrics(arm: dict) -> dict:
    """Ladder arms carry metrics either flat or under `summary`."""
    src = arm.get("summary") if isinstance(arm.get("summary"), dict) else arm
    return {
        "delivered_gold_rate": num(src.get("delivered_gold_rate")),
        "recall_at_12": num(src.get("recall_at_k")),
        "final_recall_at_12": num(src.get("final_recall_at_k")),
        "median_gold_rank": num(src.get("median_rank_of_gold")),
        "n": num(src.get("n_queries")),
        "delivered_gold_queries": num(src.get("delivered_gold_queries")),
        "gold_found_queries": num(src.get("gold_found_queries")),
    }


def parse_erb_ladders() -> None:
    """The ablation-ladder family: mirror/benchmarks/dogfood/erb/receipts/*.json.

    One measurement per (arm x receipt). The arm label is the receipt's `arm`
    field plus the arm config basename when that config is not the shipped
    cymatix.toml, because the 2026-08-27 wave-1 receipts run every arm as a full
    config file with the arm still named "baseline".
    """
    for rel in ls(ERB_DIR):
        base = os.path.basename(rel)
        try:
            doc = load(rel)
        except (ValueError, UnicodeDecodeError) as exc:
            UNPARSED.append({"receipt": rel, "reason": "json decode failed: %s" % exc})
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("arms"), list):
            continue
        arms = doc["arms"]
        if not any(isinstance(a, dict) and "arm" in a for a in arms):
            if all(isinstance(a, dict) and "label" in a and isinstance(a.get("rollup"), dict) for a in arms):
                parse_label_rollup_arms(rel, base, doc)
                continue
            UNPARSED.append(
                {
                    "receipt": rel,
                    "reason": "has an `arms` list but no `arm`-keyed entries "
                    "(keys: %s)" % sorted({k for a in arms if isinstance(a, dict) for k in a})[:8],
                }
            )
            continue
        date = derive_date(base, doc)
        bed_id = bed_id_for(doc.get("bed"), date)
        if bed_id is None:
            UNPARSED.append({"receipt": rel, "reason": "unmapped bed path %r" % doc.get("bed")})
            continue
        campaign, row, extra = campaign_for(base, date)
        cfg = os.path.basename(str(doc.get("config") or "").replace("\\", "/"))
        sha = doc.get("git_sha")
        for arm in arms:
            if not isinstance(arm, dict) or "arm" not in arm:
                continue
            met = arm_metrics(arm)
            knobs = arm.get("knobs_changed") if isinstance(arm.get("knobs_changed"), dict) else {}
            label = arm["arm"]
            if cfg and cfg != "cymatix.toml":
                label = "%s @ %s" % (label, cfg)
            shipped = bool(arm["arm"] == "baseline" and cfg == "cymatix.toml" and not knobs)
            notes = []
            if extra:
                notes.append(extra)
            if knobs:
                notes.append("knobs_changed: %s" % json.dumps(knobs, sort_keys=True))
            if met["delivered_gold_rate"] is None and met["delivered_gold_queries"] is not None:
                notes.append(
                    "receipt predates the delivered_gold_rate field; it records "
                    "delivered_gold_queries=%s of n_queries=%s"
                    % (met["delivered_gold_queries"], met["n"])
                )
            if met["final_recall_at_12"] is None:
                notes.append("receipt records no final_recall_at_k (final-order basis absent)")
            if arm.get("arm_valid") is False:
                notes.append("arm_valid=false in the receipt")
            if doc.get("bed_bytes") is not None:
                notes.append("bed_bytes at run time: %s" % doc.get("bed_bytes"))
            basis = "delivered" if met["delivered_gold_rate"] is not None else "map"
            add(
                {
                    "id": "m:%s#%s" % (base[:-5], slug(label)),
                    "date": date,
                    "bed_id": bed_id,
                    "campaign": campaign,
                    "arm": label,
                    "n": met["n"] if met["n"] is not None else num(doc.get("needle_count")),
                    "delivered_gold_rate": met["delivered_gold_rate"],
                    "recall_at_12": met["recall_at_12"],
                    "final_recall_at_12": met["final_recall_at_12"],
                    "median_gold_rank": met["median_gold_rank"],
                    "basis": basis,
                    "shipped_default": shipped,
                    "receipt": rel,
                    "baselines_row": row,
                    "pr": None,
                    "git_sha": sha,
                    "notes": " ".join(notes) or None,
                }
            )


def parse_label_rollup_arms(rel: str, base: str, doc: dict) -> None:
    """The `label` + `rollup` ablation shape (cymatics ablations), which predates
    the delivered/final split and publishes a rank-basis recall@12 only."""
    date = derive_date(base, doc)
    bed_id = bed_id_for(doc.get("genome"), date)
    if bed_id is None:
        UNPARSED.append({"receipt": rel, "reason": "unmapped bed path %r" % doc.get("genome")})
        return
    campaign, row, extra = campaign_for(base, date)
    for arm in doc["arms"]:
        roll = arm["rollup"]
        notes = [
            "rank-basis rollup; the receipt publishes %s"
            % json.dumps({k: v for k, v in roll.items() if not isinstance(v, (dict, list))}, sort_keys=True)
        ]
        if extra:
            notes.append(extra)
        if doc.get("controls"):
            notes.append("controls: %s" % doc["controls"])
        if doc.get("verdict_inputs"):
            notes.append("verdict_inputs: %s" % json.dumps(doc["verdict_inputs"], sort_keys=True))
        add(
            {
                "id": "m:%s#%s" % (base[:-5], slug(arm["label"])),
                "date": date,
                "bed_id": bed_id,
                "campaign": campaign,
                "arm": arm["label"],
                "n": num(doc.get("needles")),
                "recall_at_12": num(roll.get("recall@12")),
                "median_gold_rank": num(roll.get("median_rank")),
                "basis": "map",
                "shipped_default": arm["label"].startswith("A shipped"),
                "receipt": rel,
                "baselines_row": row,
                "git_sha": doc.get("git_sha"),
                "notes": " ".join(notes),
            }
        )


def parse_dogfood_data() -> None:
    """mirror/docs/benchmarks/data/*.json - the July dogfood ladders and baselines.

    These predate the delivered/final split: they publish a rank-basis
    `rollup["recall@12"]` over the score map, so basis is "map" and both
    delivered_gold_rate and final_recall_at_12 stay null.
    """
    for rel in ls(DATA_DIR):
        base = os.path.basename(rel)
        try:
            doc = load(rel)
        except (ValueError, UnicodeDecodeError) as exc:
            UNPARSED.append({"receipt": rel, "reason": "json decode failed: %s" % exc})
            continue
        if not isinstance(doc, dict):
            continue
        date = derive_date(base, doc)
        bed_id = bed_id_for(doc.get("genome"), date)
        campaign, row, extra = campaign_for(base, date)
        rollups: list[tuple[str, dict]] = []
        if isinstance(doc.get("rollup"), dict):
            rollups.append(("baseline", doc["rollup"]))
        for arm in doc.get("arms", []) if isinstance(doc.get("arms"), list) else []:
            if isinstance(arm, dict) and isinstance(arm.get("rollup"), dict):
                rollups.append((str(arm.get("name") or arm.get("label") or arm.get("arm")), arm["rollup"]))
        if not rollups or bed_id is None:
            continue
        for label, roll in rollups:
            r12 = num(roll.get("recall@12"))
            notes = [
                "rank-basis rollup; the receipt publishes %s"
                % json.dumps({k: v for k, v in roll.items() if not isinstance(v, (dict, list))}, sort_keys=True)
            ]
            if extra:
                notes.append(extra)
            if doc.get("scoring"):
                notes.append("scoring: %s" % doc["scoring"])
            add(
                {
                    "id": "m:%s#%s" % (base[:-5], slug(label)),
                    "date": date,
                    "bed_id": bed_id,
                    "campaign": campaign,
                    "arm": label,
                    "n": num(doc.get("needles")) or num(roll.get("needles")),
                    "recall_at_12": r12,
                    "median_gold_rank": num(roll.get("median_rank")) or num(roll.get("median_rank_when_delivered")),
                    "basis": "map",
                    "shipped_default": True if label == "baseline" else False,
                    "receipt": rel,
                    "baselines_row": row,
                    "git_sha": None,
                    "notes": " ".join(notes),
                }
            )


def parse_sike_bedsweep() -> None:
    for rel in ls(RESEARCH_DIR, "*sike_bedsweep*.json"):
        base = os.path.basename(rel)
        doc = load(rel)
        date = derive_date(base, doc)
        bed_id = bed_id_for(doc.get("bed"), date)
        if bed_id is None:
            UNPARSED.append({"receipt": rel, "reason": "unmapped bed label %r" % doc.get("bed")})
            continue
        retr = doc.get("retrieval") or {}
        campaign, row, extra = campaign_for(base, date)
        add(
            {
                "id": "m:%s#retrieval" % base[:-5],
                "date": date,
                "bed_id": bed_id,
                "campaign": campaign,
                "arm": "sike bedsweep default config",
                "n": num(doc.get("n_needles")),
                "delivered_gold_rate": num(retr.get("gold_delivered_rate")),
                "basis": "delivered",
                "shipped_default": None,
                "receipt": rel,
                "baselines_row": row,
                "git_sha": None,
                "notes": (
                    "gold_delivered_rate = gold_source_in_delivered_topK; the receipt's own note "
                    "says find_needle does not expose per-rank position so recall@k collapses for "
                    "k<=max_genes, and gold_delivered_rate is the primary retrieval metric. "
                    "gold_delivered=%s, body_has_answer_rate=%s, compression_ratio=%s."
                    % (retr.get("gold_delivered"), retr.get("body_has_answer_rate"), doc.get("compression_ratio"))
                ),
            }
        )


def parse_snow() -> None:
    for base in ("snow_oracle-only_2026-04-16.json", "snow_oracle-only_2026-04-17.json", "snow_qwen3_4b_2026-04-16.json"):
        rel = rp(SNOW_DIR, base)
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        doc = load(rel)
        meta = doc.get("meta") or {}
        oracle = doc.get("oracle") or {}
        add(
            {
                "id": "m:%s#oracle" % base[:-5],
                "date": derive_date(base, doc),
                "bed_id": "snow_genome",
                "campaign": "2026-04-snow-harness",
                "arm": str(meta.get("model")),
                "n": num(meta.get("n_queries")),
                "basis": None,
                "shipped_default": None,
                "receipt": rel,
                "baselines_row": None,
                "git_sha": None,
                "notes": (
                    "Snow-harness era receipt: it publishes no delivered/recall metric in this "
                    "ledger's vocabulary. Receipt values: oracle.miss_rate=%s, oracle.avg_tier=%s, "
                    "oracle.avg_tokens=%s, gene_count=%s. Recorded so the snow family is not "
                    "silently absent; every metric field is null by design."
                    % (oracle.get("miss_rate"), oracle.get("avg_tier"), oracle.get("avg_tokens"), meta.get("gene_count"))
                ),
            }
        )


def parse_v091_gate() -> None:
    rel = rp(DOGFOOD_RECEIPTS, "sweep_v091_gate_2026-08-30.json")
    doc = load(rel)
    beds = {
        "enronqa_v2": "enronqa_v2",
        "enronqa_padded": "enronqa_padded",
        "erb_100k": "erb_100k",
        "erb_829k": "erb_blob_v09x_947k",
    }
    row = "2026-08-30-v091-gate-sweep"
    for key in sorted(doc.get("beds", {})):
        cell = doc["beds"][key]
        bed_id = beds.get(key)
        if bed_id is None:
            UNPARSED.append({"receipt": rel, "reason": "unmapped bed key %r" % key})
            continue
        if key == "erb_829k":
            for arm_label, field in (
                ("v091 shipped defaults", "v091_delivered"),
                ("v090 frozen defaults", "frozen_v090_delivered"),
                ("wave-1 frozen combo", "frozen_wave1_delivered"),
            ):
                add(
                    {
                        "id": "m:sweep_v091_gate#%s-%s" % (key, slug(arm_label)),
                        "date": "2026-08-30",
                        "bed_id": bed_id,
                        "campaign": row,
                        "arm": arm_label,
                        "n": None,
                        "delivered_gold_rate": num(cell.get(field)),
                        "basis": "delivered",
                        "shipped_default": arm_label.startswith("v091"),
                        "receipt": rel,
                        "baselines_row": row,
                        "git_sha": doc.get("integration_commit"),
                        "notes": (
                            "Decision metric is delivered_gold_rate (receipt's own "
                            "decision_metric field). This cell records only delivered rates: "
                            "lift_over_v090=%s, reproduce_delta_vs_wave1=%s, status=%s. n is not "
                            "stated in this block; the BASELINES row gives n=470 for the v09x set."
                            % (cell.get("lift_over_v090"), cell.get("reproduce_delta_vs_wave1"), cell.get("status"))
                        ),
                    }
                )
            continue
        for arm_key, arm_label in (("v090", "v090 frozen defaults"), ("v091", "v091 shipped defaults")):
            block = cell.get(arm_key) or {}
            paired = cell.get("paired_delivered") or {}
            para = (cell.get("paraphrase_delivered") or {}).get(arm_key)
            notes = [
                "paired delivered vs the other arm: n_paired=%s gained=%s lost=%s net=%s; status=%s."
                % (paired.get("n_paired"), paired.get("gained"), paired.get("lost"), paired.get("net"), cell.get("status"))
            ]
            if para:
                notes.append("paraphrase delivered original=%s rephrased=%s." % (para.get("orig"), para.get("reph")))
            add(
                {
                    "id": "m:sweep_v091_gate#%s-%s" % (key, arm_key),
                    "date": "2026-08-30",
                    "bed_id": bed_id,
                    "campaign": row,
                    "arm": arm_label,
                    "n": num(paired.get("n_paired")),
                    "delivered_gold_rate": num(block.get("delivered_gold_rate")),
                    "recall_at_12": num(block.get("recall_at_k")),
                    "final_recall_at_12": num(block.get("final_recall_at_k")),
                    "median_gold_rank": num(block.get("median_rank_of_gold")),
                    "basis": "delivered",
                    "shipped_default": arm_key == "v091",
                    "receipt": rel,
                    "baselines_row": row,
                    "git_sha": doc.get("integration_commit"),
                    "notes": " ".join(notes),
                }
            )
        floor = cell.get("v091_floor_informational")
        if floor:
            fp = floor.get("paired_vs_v091") or {}
            add(
                {
                    "id": "m:sweep_v091_gate#%s-v091_floor" % key,
                    "date": "2026-08-30",
                    "bed_id": bed_id,
                    "campaign": row,
                    "arm": "v091 + min_delivered_docs floor 12 (informational)",
                    "n": num(fp.get("n_paired")),
                    "delivered_gold_rate": num(floor.get("delivered_gold_rate")),
                    "basis": "delivered",
                    "shipped_default": False,
                    "receipt": rel,
                    "baselines_row": row,
                    "git_sha": doc.get("integration_commit"),
                    "notes": (
                        "Informational arm for issue #409 (W2.4 seat floor). Paired vs v091: "
                        "gained=%s lost=%s net=%s over n_paired=%s."
                        % (fp.get("gained"), fp.get("lost"), fp.get("net"), fp.get("n_paired"))
                    ),
                }
            )


def parse_entity_hub_ab() -> None:
    rel = rp(DOGFOOD_RECEIPTS, "entity_hub_cutoff_retrieval_ab_enronqa_2026-08-30.json")
    doc = load(rel)
    row = "2026-08-30-entity-hub-cutoff-retrieval-ab"
    beds = {"v2": "enronqa_v2", "v2c": "enronqa_v2c"}
    # the receipt labels the two beds under keys "a" and "b"
    bed_labels = {"v2": doc["beds"]["a"], "v2c": doc["beds"]["b"]}
    for arm_key in sorted(doc.get("arms", {})):
        arm = doc["arms"][arm_key]
        for bed_key in ("v2", "v2c"):
            block = arm.get(bed_key) or {}
            add(
                {
                    "id": "m:entity_hub_cutoff_retrieval_ab#%s-%s" % (arm_key, bed_key),
                    "date": "2026-08-30",
                    "bed_id": beds[bed_key],
                    "campaign": row,
                    "arm": "%s config on %s" % (arm_key, bed_labels[bed_key]),
                    "n": 500,
                    "delivered_gold_rate": num(block.get("delivered_gold_rate")),
                    "recall_at_12": num(block.get("recall_at_k")),
                    "final_recall_at_12": num(block.get("final_recall_at_k")),
                    "median_gold_rank": num(block.get("median_rank_of_gold")),
                    "basis": "delivered",
                    "shipped_default": arm_key == "v091",
                    "receipt": rel,
                    "baselines_row": row,
                    "pr": 412,
                    "git_sha": None,
                    "notes": (
                        "n=500 is the committed EnronQA needle set named in the BASELINES row "
                        "(the receipt itself states per_needle_delivered_flips=%s and "
                        "null_confirmed=%s but no n field). PR number from the BASELINES row: "
                        "'perf+edge-delta receipts: PR #412 / issue #411'."
                        % (arm.get("per_needle_delivered_flips"), arm.get("null_confirmed"))
                    ),
                }
            )


def parse_sema_ingest_ab() -> None:
    rel = rp(DOGFOOD_RECEIPTS, "sema_ingest_ab_dogfood.json")
    doc = load(rel)
    row = "2026-08-19-sema-ingest-ab"
    roll = doc["results"]["rollup"]
    for arm_key, label, shipped in (
        ("A", "A_sema_on (dense ingest off, sema on)", True),
        ("B", "B_sema_off (both ingest knobs false)", False),
    ):
        add(
            {
                "id": "m:sema_ingest_ab_dogfood#arm_%s" % arm_key.lower(),
                "date": "2026-08-19",
                "bed_id": "dogfood_sema_ab",
                "campaign": row,
                "arm": label,
                "n": 18,
                "delivered_gold_rate": num(roll["delivered_gold_rate"][arm_key]),
                "recall_at_12": num(roll["pool_recall_at_12"][arm_key]),
                "final_recall_at_12": num(roll["final_recall_at_12"][arm_key]),
                "basis": "delivered",
                "shipped_default": shipped,
                "receipt": rel,
                "baselines_row": row,
                "git_sha": doc.get("git_sha"),
                "notes": (
                    "n=18 needles from the BASELINES row (the receipt states the rollup rates, not "
                    "n). packet_delivered_gold_rate=%s, sema_boost fired on %s of 18 queries. "
                    "Verdict in the receipt: %s"
                    % (
                        roll["packet_delivered_gold_rate"][arm_key],
                        roll["sema_boost_fired_queries"][arm_key],
                        doc.get("verdict", "")[:160],
                    )
                ),
            }
        )


def parse_tagger_v2() -> None:
    rel = rp(DOGFOOD_RECEIPTS, "tagger_v2_entity_hygiene_2026-08-30.json")
    doc = load(rel)
    delta = doc["delta"]
    for arm_key, label in (("v1", "tagger v1 (entity-hygiene gate bypassed)"), ("v2", "tagger v2 (shipped)")):
        block = doc[arm_key]
        add(
            {
                "id": "m:tagger_v2_entity_hygiene#%s" % arm_key,
                "date": "2026-08-30",
                "bed_id": None,
                "campaign": "2026-08-30-tagger-v2-entity-hygiene",
                "arm": label,
                "n": None,
                "basis": None,
                "shipped_default": arm_key == "v2",
                "receipt": rel,
                "baselines_row": None,
                "git_sha": None,
                "notes": (
                    "Ingest-side receipt: no retrieval metric, so every rate field is null. "
                    "2,000-file sample over the EnronQA corpus+padding roots (seed 20260830), "
                    "genes=%s, entity_graph_rows=%s, distinct_entities=%s, "
                    "multiline_entity_kinds=%s. Arm delta across the pair: entity_graph_rows %s "
                    "(%s%%), distinct_entities_removed %s. This receipt is what the BASELINES.md "
                    "tagger-version rule cites for the v1->v2 delta; it makes every pre-2026-08-30 "
                    "bed tagger_version=1 and not cross-comparable with v2 beds."
                    % (
                        block["genes"],
                        block["entity_graph_rows"],
                        block["distinct_entities"],
                        block["multiline_entity_kinds"],
                        delta["entity_graph_rows"],
                        delta["entity_graph_rows_pct"],
                        delta["distinct_entities_removed"],
                    )
                ),
            }
        )


def add_curated_measurements() -> None:
    """Rows whose numbers live in a BASELINES.md row or a research-inbox capture
    rather than in a mirrored receipt. Each names its source explicitly."""

    row = "2026-08-29-enronqa-native-baseline"
    add(
        {
            "id": "m:baselines#enronqa-native-baseline-2026-08-29",
            "date": "2026-08-29",
            "bed_id": "enronqa_native",
            "campaign": row,
            "arm": "post-#407 shipped defaults (config sha 41a258c6...)",
            "n": 500,
            "delivered_gold_rate": 0.820,
            "recall_at_12": 0.876,
            "final_recall_at_12": 0.872,
            "median_gold_rank": 3.0,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": None,
            "baselines_row": row,
            "git_sha": "ab3dac4",
            "notes": (
                "Numbers quoted from the BASELINES.md row; the row's own receipt "
                "benchmarks/dogfood/enronqa/receipts/ladder_enronqa_native_baseline_2026-08-29.json "
                "is NOT in the mirror (see `missing`). pool_delivery_gap 0.056."
            ),
        }
    )
    add(
        {
            "id": "m:baselines#enronqa-native-original-2026-08-29",
            "date": "2026-08-29",
            "bed_id": "enronqa_native",
            "campaign": row,
            "arm": "post-#407 shipped defaults, ORIGINAL half of each needle pair",
            "n": 250,
            "delivered_gold_rate": 0.840,
            "recall_at_12": 0.904,
            "final_recall_at_12": 0.896,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": None,
            "baselines_row": row,
            "git_sha": "ab3dac4",
            "notes": (
                "Paraphrase crater, original half. BASELINES row: 'original 0.904/0.896/0.840 vs "
                "rephrased 0.848/0.848/0.800 -> paraphrase gap -5.6pp map / -4.8pp fr / -4.0pp "
                "delivered'. n=250 is half the 500-needle set (250 pairs). Receipt not mirrored."
            ),
        }
    )
    add(
        {
            "id": "m:baselines#enronqa-native-rephrased-2026-08-29",
            "date": "2026-08-29",
            "bed_id": "enronqa_native",
            "campaign": row,
            "arm": "post-#407 shipped defaults, REPHRASED half of each needle pair",
            "n": 250,
            "delivered_gold_rate": 0.800,
            "recall_at_12": 0.848,
            "final_recall_at_12": 0.848,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": None,
            "baselines_row": row,
            "git_sha": "ab3dac4",
            "notes": (
                "Paraphrase crater, rephrased half. Contingency on delivered (BASELINES row): 182 "
                "both / 28 original-only / 18 rephrased-only / 22 both-miss; dual-found rank delta "
                "mean +0.93, median 0. Receipt not mirrored."
            ),
        }
    )

    add(
        {
            "id": "m:research-inbox#erb-basic-miss-taxonomy-2026-08-31",
            "date": "2026-08-31",
            "bed_id": "erb_blob_v09x_947k",
            "campaign": "2026-08-31-basic-miss-taxonomy",
            "arm": "shipped v0.9.1 defaults + min_delivered floor 12, question_type=basic subset",
            "n": 175,
            "delivered_gold_rate": None,
            "recall_at_12": None,
            "final_recall_at_12": None,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": "research-inbox/2026-08-31-basic-miss-taxonomy.json",
            "baselines_row": None,
            "git_sha": None,
            "notes": (
                "Class-scoped re-analysis of ladder_v09x_w24_min_delivered_2026-08-28.json arm[0]. "
                "The capture publishes counts, not rates, so the rate fields stay null: n_basic=175, "
                "n_delivered_hits=115, n_misses=60; map_recall r@2=78 r@5=103 r@12=120, "
                "gold_found_anywhere=138, delivered=115. Miss rank buckets: absent=37, 13-30=13, "
                "31-100=5, <=12=5. Reachability: all 37 pool-absent basic golds return on a 6-gram "
                "FTS5 phrase probe."
            ),
        }
    )
    add(
        {
            "id": "m:research-inbox#muloc-delivered6-cohort-2026-08-31",
            "date": "2026-08-31",
            "bed_id": "muloc",
            "campaign": "2026-08-31-representation-campaign-synthesis",
            "arm": "shipped defaults, delivered_count=6 cohort",
            "n": 226,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
            "baselines_row": None,
            "git_sha": None,
            "notes": (
                "Prose-only cohort row, no rate published: 'MULoc delivered_count=6 cohort | 226 | "
                "15%-of-top hard floor, NOT tokens (14000 null receipt)'. The cited receipt "
                "benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json is not "
                "in the mirror (see `missing`)."
            ),
        }
    )
    add(
        {
            "id": "m:research-inbox#financebench-metrics-class-2026-08-31",
            "date": "2026-08-31",
            "bed_id": "financebench",
            "campaign": "2026-08-31-representation-campaign-synthesis",
            "arm": "shipped defaults, metrics question class",
            "n": 50,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
            "baselines_row": None,
            "git_sha": None,
            "notes": (
                "Prose-only cohort row: 'FinanceBench metrics class | 50 (0 hits) | doc-identity x "
                "concept intersection inexpressible in flat FTS'. Zero hits on 50 queries; the "
                "synthesis calls it the FinanceBench baseline blackout. No receipt in the mirror."
            ),
        }
    )
    add(
        {
            "id": "m:research-inbox#locomo-cognitive-cohort-2026-08-31",
            "date": "2026-08-31",
            "bed_id": "locomo",
            "campaign": "2026-08-31-representation-campaign-synthesis",
            "arm": "shipped defaults, cognitive question class",
            "n": 401,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
            "baselines_row": None,
            "git_sha": None,
            "notes": (
                "Prose-only cohort row: 'LoCoMo cognitive | 401 (3 hits) | cue-trigger disconnect; "
                "dense fails too | provenance-linked observation lane only'. The three-way "
                "LoCoMo / LoCoMo+obs comparison has no receipt in the mirror (see `missing`)."
            ),
        }
    )

    add(
        {
            "id": "m:untracked#verify-p0p3p5-basis-2026-09-01",
            "date": "2026-09-01",
            "bed_id": "erb_blob_v09x_947k",
            "campaign": "2026-09-01-erb-phase2-adversarial-verification",
            "arm": "A5-verify (read-only re-derivation of the Phase-1 probes)",
            "n": 156,
            "delivered_gold_rate": 0.668085,
            "basis": "delivered",
            "shipped_default": True,
            "receipt": "untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
            "baselines_row": None,
            "git_sha": "6268b6fa67c09d0f9026a18933b3b11c10e19614",
            "notes": (
                "Not a mirrored receipt: it lives under untracked/ because it postdates the mirror "
                "commit. n=156 is the mined miss set (n_misses), not a needle count; the baseline "
                "it re-derives is the 470-needle w24 floor arm and it recomputes that arm's "
                "delivered rate independently as 0.668085 (baseline_rate_recomputed), matching "
                "ladder_v09x_w24_min_delivered_2026-08-28.json 0.6680851063829787. Corpus scan: "
                "947,531 chunks / 500,000 docs / 386 gold chunks."
            ),
        }
    )


# ---------------------------------------------------------------- kills

KILLS = [
    {
        "id": "k:2026-08-14-dense-default-on",
        "date": "2026-08-14",
        "lever": "dense (BGE-M3) retrieval enabled by default",
        "bed_id": "erb_blob_829k",
        "kill_criterion": None,
        "result": (
            "dense_on loses gold from the delivered window at every scale: delivered_gold_rate "
            "0.8333->0.5000 (100k), 0.8000->0.4667 (250k), 0.7333->0.4000 (500k), 0.7000->0.5000 "
            "(829k n=30), and 0.5629->0.4222 at 829k n=469, with final_recall_at_12 0.6631->0.4563."
        ),
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/enc_iso_829k_dense_confirm_run1.json",
        "verdict": "KILL",
        "notes": (
            "Carve-scale numbers from enc_iso_{100k,250k,500k}_run1_fwd.json and "
            "enc_iso_829k_run1_fwd.json; the n=469 confirm from the receipt named above. Both run "
            "orders reproduce exactly. BASELINES row 2026-08-14-encoder-isolation. The receipt has "
            "no kill_criterion field."
        ),
    },
    {
        "id": "k:2026-08-15-splade-expansion",
        "date": "2026-08-15",
        "lever": "SPLADE sparse expansion",
        "bed_id": "erb_blob_829k",
        "kill_criterion": None,
        "result": (
            "splade_on delivered_gold_rate 0.5480 (257/469) vs floor 0.5629 (264/469), -7 needles; "
            "r@12 0.6546 vs 0.6588 and fr@12 0.6567 vs 0.6631. On the nosplade bed the arm is "
            "byte-identical to the floor (0.5629 = 0.5629, r@12 and fr@12 identical), so the index "
            "contributes nothing passively."
        ),
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/enc_iso_829k_splade_confirm_run1.json",
        "verdict": "KILL",
        "notes": (
            "The null-when-absent half is enc_iso_829k_nosplade_run1.json / _run2.json. The "
            "2026-08-14 write-up records that the earlier prose credited SPLADE with +0.033 at "
            "250k on the final-order basis; the 2026-08-19 (#375) correction shows that on the "
            "delivered basis 250k is SPLADE's worst cell (0.667 vs 0.800, -0.133)."
        ),
    },
    {
        "id": "k:2026-08-17-pki-path-key-index",
        "date": "2026-08-17",
        "lever": "path_key_index (PKI) Tier-0 lookup",
        "bed_id": "erb_829k_nosplade",
        "kill_criterion": None,
        "result": (
            "Shipped config with PKI on delivered 263/469 (0.5608); the no_pki arm delivered "
            "264/469 (0.5629) with r@12 0.6588 vs 0.6546 and fr@12 0.6631 vs 0.6588 - PKI costs "
            "one delivered needle."
        ),
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/postflip_default_confirm_829k.json",
        "verdict": "KILL",
        "notes": "Default flipped to false under issue #370. The receipt carries no kill_criterion field.",
    },
    {
        "id": "k:2026-08-19-neutralize-control-tags",
        "date": "2026-08-19",
        "lever": "budget.neutralize_control_tags",
        "bed_id": "erb_100k",
        "kill_criterion": None,
        "result": (
            "Exact null: r@12 0.6879 = 0.6879, fr@12 0.6950 = 0.6950, delivered_gold_rate "
            "0.6099 = 0.6099, 141/141 windows byte-identical, 0 rank-or-delivery mismatches."
        ),
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/neutralize_ab_100k.json",
        "verdict": "NULL",
        "notes": (
            "The bed scan found zero control-tag documents, so the positive case rests on the "
            "synthetic unit tests, disclosed in the receipt note. Issue #351; the default was "
            "flipped to true in the same PR despite the null."
        ),
    },
    {
        "id": "k:2026-08-28-w2.1-cover-graph-walk",
        "date": "2026-08-28",
        "lever": "W2.1 query-time COVER graph walk (cover_walk_enabled)",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": (
            "Zero delivered gain and a final-order loss: delivered_gold_rate 0.6297872340425532, "
            "identical to the wave-1 combo arm to full precision, while final_recall_at_12 falls "
            "0.6830 -> 0.6553 at n=470 (r@12 unchanged at 0.6809, median gold rank 2.0)."
        ),
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/ladder_v09x_w2_cover_walk_2026-08-28.json",
        "verdict": "KILL",
        "notes": (
            "Comparator is ladder_v09x_w1c_k20_eps_all_full_2026-08-28.json (delivered "
            "0.6297872340425532, fr@12 0.6830) on the same bed and needle set. Preflight "
            "reachability receipt: w2_cover_reachability_preflight_2026-08-28.json. The receipt "
            "has no verdict or kill_criterion field; the KILL label is this ledger's reading of "
            "the paired deltas."
        ),
    },
    {
        "id": "k:2026-08-30-entity-hub-cutoff-retrieval",
        "date": "2026-08-30",
        "lever": "entity_autolink_hub_cutoff=200 (retrieval-side effect)",
        "bed_id": "enronqa_v2c",
        "kill_criterion": (
            "expectation stated in the receipt: 'null deltas at shipped defaults (COVER edges query-inert)'"
        ),
        "result": (
            "NULL confirmed in both configs: v090 and v091 each give delivered 0.694 / 0.820, "
            "r@12 0.784 / 0.876, fr@12 0.788 / 0.872 on both beds, with per_needle_delivered_flips "
            "= 0 of 500 and an empty flip list."
        ),
        "receipt": "mirror/benchmarks/dogfood/receipts/entity_hub_cutoff_retrieval_ab_enronqa_2026-08-30.json",
        "verdict": "NULL",
        "notes": (
            "The two beds have identical gene-id-set digests, so this isolates the COVER-edge "
            "difference. The lever earns its flip on build cost (PR #412 / issue #411), not on "
            "retrieval."
        ),
    },
    {
        "id": "k:2026-07-29-cymatics-as-semantic-signal",
        "date": "2026-07-29",
        "lever": "cymatics 256-bin spectrum scoring as a semantic signal",
        "bed_id": "dogfood_clean",
        "kill_criterion": None,
        "result": (
            "Indistinguishable from its own controls: verdict_inputs give A_recall@12 0.6667, "
            "B_off_recall@12 0.6667, C_bow_recall@12 0.6667 and D_random_recall@12_mean 0.6667 "
            "(random spread 0.6667-0.6667); MRR A 0.4592 sits inside the random band 0.4456-0.4734."
        ),
        "receipt": "mirror/docs/benchmarks/data/2026-07-29-cymatics-ablation-clean.json",
        "verdict": "NULL",
        "notes": (
            "The pre-clean-bed run (2026-07-29-cymatics-ablation.json) reports the same four-way "
            "tie at recall@12 0.6667 with A_mrr 0.4456. Reconfirmed at ERB scale on 2026-08-09 "
            "(wave3d_cymatics_354_100k_carve.json, erb_100k n=141, issue #354): A/B/C/D all "
            "recall@12 0.6879, A_mrr 0.5011 against a random-bin band of 0.4964-0.4999. Write-up: "
            "mirror/docs/benchmarks/2026-07-29-cymatics-ablation-verdict.md."
        ),
    },
    {
        "id": "k:2026-09-01-head-chunk-monopoly",
        "date": "2026-09-01",
        "lever": "head-chunk monopoly at rank 1 (Phase-1 probe P5 bottom line)",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": (
            "quoted from the receipt: \"Per probe: REFUTED if the probe's own coded/pre-registered "
            "decision rule flips once a defect is corrected, OR if its headline number is pinned by "
            "construction (measured against a null with no support on this bed). ... Arm verdict: "
            "KILL if any probe is REFUTED, PASS if all three CONFIRMED, INCONCLUSIVE if corrections "
            "were needed but the conclusions stand.\""
        ),
        "result": (
            "REFUTED as a presentation-order artifact: the 156/156 head-or-only result at p=1.122e-19 "
            "measured the assembler's sequence_index sort, so seat 1 is head-or-only with "
            "probability 1. In true score order it is 79.49%, and inside the pool rank carries no "
            "head-chunk information (17.29% middle share at rank 1 vs 17.47% at ranks 2-15). What "
            "survives is an admission effect: at-cap head chunks enter the pool about 1.4x more "
            "often than equally long middle chunks (obs/exp 0.592 at rank 1, z=-3.72)."
        ),
        "receipt": "untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
        "verdict": "REFUTED",
        "notes": (
            "Receipt verdict field: KILL. It is under untracked/ rather than mirror/ because it "
            "postdates the mirror commit. Its basis_receipts name three Phase-1 probe receipts that "
            "are not in this archive at all (see `missing`)."
        ),
    },
    {
        "id": "k:2026-09-01-p0-chunk-split-count",
        "date": "2026-09-01",
        "lever": "chunk_split bucket count in the Phase-1 bucket ledger (probe P0)",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": (
            "quoted from the receipt: 'CORRECTED if a headline number or a stated definition is "
            "wrong but the probe's verdict on its own pre-registered criterion still stands.'"
        ),
        "result": (
            "Ledger sound, count wrong: the buckets reproduce exactly from the raw mine (n=156) and "
            "rloss.py passes an independent reimplementation plus 200 randomised negative-control "
            "trials with zero mismatches, but chunk_split is 65/156 only under an arbitrary "
            "hash-ordered gold chunk; under the definition the receipt states (gold's best single "
            "chunk) it is 30/156 and 16/95 reachable."
        ),
        "receipt": "untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
        "verdict": "CORRECTED",
        "notes": (
            "Same root cause corrects a second published magnitude: gold at-cap rate 42.9% (an "
            "arbitrary gold chunk) becomes 54.4% over all 386 gold chunks. Probe P3 "
            "(scope_verbosity) came back CONFIRMED with corrections and is therefore not recorded "
            "as a kill."
        ),
    },
    {
        "id": "k:2026-09-01-phrase-near-lane",
        "date": "2026-09-01",
        "lever": "exact-phrase + NEAR lane fused into RRF",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": (
            "Discrimination, not reachability: reach is fine (31/37 basic pool-absent reachable, "
            "94.2% of all misses with the DF cap lifted) but the phrase fire rate is 0.9126 on "
            "standardised hits vs 0.7372 on misses - inverted, negative at every k, in all 7 "
            "strata; bootstrap 95% CI [-0.2616, -0.0855], P(delta >= +0.10) = 0.0000."
        ),
        "receipt": None,
        "verdict": "KILL",
        "notes": (
            "Numbers quoted from research-inbox/2026-09-01-phase2-handoff.md, 'Killed in Phase 1' "
            "table. The underlying phrase_reach probe receipt is not in this archive (see "
            "`missing`), so this entry is prose-sourced and cannot be re-derived from the clone."
        ),
    },
    {
        "id": "k:2026-09-01-phrase-as-rerank-feature",
        "date": "2026-09-01",
        "lever": "phrase presence as a re-ranking feature",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": (
            "Gold out-phrases the best already-delivered chunk on only 29/156 (18.6%); it ties on "
            "78 and loses on 49, and the control is generous to gold because gold chunks are 17% "
            "shorter on a length-monotone statistic."
        ),
        "receipt": None,
        "verdict": "KILL",
        "notes": "Quoted from research-inbox/2026-09-01-phase2-handoff.md. No probe receipt in this archive.",
    },
    {
        "id": "k:2026-09-01-doc-rollup-aggregation",
        "date": "2026-09-01",
        "lever": "doc-rollup / chunk aggregation to source_id",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": (
            "UNION doc rank-1 is 17/156 against an analytic random baseline of 15.6 - "
            "indistinguishable from a shuffle - and a realizable rollup over the real score pool "
            "nets one new rescue. The corpus averages 1.895 chunks per doc with 78.6% of docs at "
            "two chunks or fewer."
        ),
        "receipt": None,
        "verdict": "KILL",
        "notes": (
            "Quoted from research-inbox/2026-09-01-phase2-handoff.md. The doc_union_oracle probe "
            "receipt is not in this archive (see `missing`)."
        ),
    },
    {
        "id": "k:2026-09-01-length-normalization",
        "date": "2026-09-01",
        "lever": "length-normalization family (BM25 b, rank-time length penalty)",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": (
            "The mechanism is absent: verbosity runs backwards (winner/gold/corpus avg_tf "
            "1.541/1.571/1.691) and boilerplate fires at 0.0%. Gold is not short - 47.8% of the "
            "corpus sits at the 4,000-char cap so gold's 42.9% is the base rate; the anomaly is "
            "entirely winner-side at 1.80x."
        ),
        "receipt": None,
        "verdict": "KILL",
        "notes": (
            "Quoted from research-inbox/2026-09-01-phase2-handoff.md. The scope_verbosity and "
            "atcap_confound probe receipts are not in this archive; the 2026-09-01 verification "
            "receipt later corrected the 42.9% figure to 54.4% over all gold chunks."
        ),
    },
    {
        "id": "k:2026-08-31-w2.2-in-band-coverage-tiebreak",
        "date": "2026-08-31",
        "lever": "W2.2 in-band (eps_band) coverage tie-break",
        "bed_id": "erb_blob_v09x_947k",
        "kill_criterion": None,
        "result": "Killed on band geometry at rrf_k=20; no numbers are published in any source held in this archive.",
        "receipt": None,
        "verdict": "KILL",
        "notes": (
            "Named in the killed list of research-inbox/2026-09-01-architecture-hunt-prompt.md "
            "('W2.2 in-band coverage tie-break (band geometry at rrf_k=20)'). The 2026-08-31 "
            "synthesis still describes the W2.2 arm as running on the 470-needle set. No W2.2 "
            "receipt exists in this archive, so no metric is recorded."
        ),
    },
    {
        "id": "k:2026-08-31-gated-dense-fallback",
        "date": "2026-08-31",
        "lever": "gated dense fallback for the semantic class (dense-ceiling probe)",
        "bed_id": "erb_blob_829k",
        "kill_criterion": None,
        "result": (
            "Ceiling measured at 4/86 semantic needles at k=12 with a median dense rank of 3,020, "
            "so a gated fallback cannot pay."
        ),
        "receipt": None,
        "verdict": "KILL",
        "notes": (
            "Quoted from the killed list of research-inbox/2026-09-01-architecture-hunt-prompt.md, "
            "which names the receipt dense_ceiling_probe_829k. That receipt is not in this archive "
            "(see `missing`); the bed_id is this ledger's reading of the '829k' in the receipt name "
            "and is not confirmed by a mirrored file."
        ),
    },
    {
        "id": "k:2026-08-31-muloc-budget-14000",
        "date": "2026-08-31",
        "lever": "expression_tokens raised to 14000 on MULocBench",
        "bed_id": "muloc",
        "kill_criterion": None,
        "result": (
            "Null: the 226-query delivered_count=6 cohort is bound by a 15%-of-top hard floor, not "
            "by the token budget."
        ),
        "receipt": None,
        "verdict": "NULL",
        "notes": (
            "Quoted from research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md, which "
            "cites benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json. "
            "That receipt is not in this archive (see `missing`), and no rate is published in the "
            "prose."
        ),
    },
]


# ---------------------------------------------------------------- graduations

GRADUATIONS = [
    {
        "id": "g:2026-08-15-dense-default-off",
        "date": "2026-08-15",
        "change": "retrieval.dense_embedding_enabled true -> false (default OFF)",
        "bed_id": "erb_blob_829k",
        "delivered_before": 0.42217484008528783,
        "delivered_after": 0.5628997867803838,
        "paired": None,
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/enc_iso_829k_dense_confirm_run1.json",
        "notes": (
            "before = the dense_on arm, after = the all-off floor, n=469, both from the named "
            "receipt and reproduced exactly in _run2. The receipt publishes no paired per-needle "
            "gained/lost block. BASELINES row 2026-08-14-encoder-isolation records the flip as "
            "merged to master via the #363-#369 stack with no frozen tag."
        ),
    },
    {
        "id": "g:2026-08-16-splade-default-off",
        "date": "2026-08-16",
        "change": "ingestion.splade_enabled true -> false (default OFF)",
        "bed_id": "erb_blob_829k",
        "delivered_before": 0.5479744136460555,
        "delivered_after": 0.5628997867803838,
        "paired": None,
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/enc_iso_829k_splade_confirm_run1.json",
        "notes": (
            "before = splade_on (257/469), after = floor (264/469), n=469, reproduced exactly in "
            "_run2. No paired block in the receipt."
        ),
    },
    {
        "id": "g:2026-08-19-pki-default-off",
        "date": "2026-08-19",
        "change": "retrieval.pki_enabled true -> false (default OFF, issue #370)",
        "bed_id": "erb_829k_nosplade",
        "delivered_before": 0.5607675906183369,
        "delivered_after": 0.5628997867803838,
        "paired": None,
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/postflip_default_confirm_829k.json",
        "notes": (
            "before = the baseline arm with PKI on (263/469), after = the no_pki arm (264/469), "
            "n=469. Issue number from the BASELINES bed-state note; no PR number is stated in any "
            "mirrored source, so pr stays null."
        ),
    },
    {
        "id": "g:2026-08-19-sema-ingest-default-off",
        "date": "2026-08-19",
        "change": "ingestion.sema_embed_on_ingest true -> false (default OFF, issue #371)",
        "bed_id": "erb_829k_nosplade",
        "delivered_before": 0.5628997867803838,
        "delivered_after": 0.5650319829,
        "paired": "+1/-0",
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/sema_readgate_829k_n469.json",
        "notes": (
            "The deciding cell. before = baseline_summary (paired against arm no_pki of "
            "postflip_default_confirm_829k.json), after = the no_sema_readgate arm: 265/469 vs "
            "264/469, r@12 0.6588 / fr@12 0.6631 / median rank 3.0 identical, paired flips 1 "
            "gained (erb_407, budget boundary) and 0 lost with 0 final-rank moves. The dogfood A/B "
            "(sema_ingest_ab_dogfood.json) disagreed at n=18 with delivered 0.7222 -> 0.6111 and "
            "returned ESCALATE; the 829k cell settled it."
        ),
    },
    {
        "id": "g:2026-08-19-neutralize-control-tags-on",
        "date": "2026-08-19",
        "change": "budget.neutralize_control_tags false -> true (issue #351)",
        "bed_id": "erb_100k",
        "delivered_before": 0.6099,
        "delivered_after": 0.6099,
        "paired": "+0/-0",
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/neutralize_ab_100k.json",
        "notes": (
            "Flipped on a measured null (a safety change, not a recall change): 141/141 windows "
            "byte-identical and 0 rank-or-delivery mismatches. The '+0/-0' is the receipt's "
            "comparison block (mismatch_count 0), not a gained/lost tally."
        ),
    },
    {
        "id": "g:2026-08-28-wave1-ranking-under-width",
        "date": "2026-08-28",
        "change": "rrf_k 60 -> 20 + all-five-classes eps_band rerank_combinator_by_class",
        "bed_id": "erb_blob_v09x_947k",
        "delivered_before": 0.5553191489361702,
        "delivered_after": 0.6297872340425532,
        "paired": "+43/-8",
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/ladder_v09x_w1c_k20_eps_all_full_2026-08-28.json",
        "notes": (
            "before = ladder_v09x_w1c_baseline_full_2026-08-28.json (261/470), after = the named "
            "combo confirm (296/470), n=470. Paired counts, r@12 0.651->0.681 (+18/-4) and median "
            "rank 3->2 are quoted from the BASELINES row 2026-08-27-ranking-under-width-wave1, "
            "which marks the change GRADUATED under its rule 6; the receipts carry the rates and "
            "the per_query vectors but not the gained/lost summary. No PR number appears in any "
            "mirrored source."
        ),
    },
    {
        "id": "g:2026-08-30-w2.4-min-delivered-floor",
        "date": "2026-08-30",
        "change": "budget.min_delivered_docs 0 -> 12 (W2.4 seat floor, issue #409)",
        "bed_id": "erb_blob_v09x_947k",
        "delivered_before": 0.6297872340425532,
        "delivered_after": 0.6680851063829787,
        "paired": "+18/-0",
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/erb/receipts/ladder_v09x_w24_min_delivered_2026-08-28.json",
        "notes": (
            "before = the wave-1 combo arm (296/470), after = the floor arm (314/470), n=470, "
            "r@12 0.6809 and fr@12 0.6830 unchanged - the floor moves delivery only. The +18/-0 "
            "paired figure and the two cross-corpus confirms (+18/-0 enronqa_v2, +8/-0 "
            "enronqa_padded) are from sweep_v091_gate_2026-08-30.json, where the arm is labelled "
            "informational; the BASELINES v0.9.1 row records 'three corpora, zero paired losses'."
        ),
    },
    {
        "id": "g:2026-08-30-tagger-v2-entity-hygiene",
        "date": "2026-08-30",
        "change": "CpuTagger TAGGER_VERSION 1 -> 2 (entity-hygiene fix, issue #410)",
        "bed_id": None,
        "delivered_before": None,
        "delivered_after": None,
        "paired": None,
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/receipts/tagger_v2_entity_hygiene_2026-08-30.json",
        "notes": (
            "Ingest-side graduation with no retrieval measurement, so the delivered fields are "
            "null. On a 2,000-file EnronQA sample the fix removes 5,835 entity_graph rows "
            "(-16.66%) and 1,989 distinct entities, all MIME/header noise (content-type, "
            "content-transfer-encoding, javamail, x-origin), and eliminates every multiline entity "
            "(1,974 kinds / 2,818 occurrences -> 0). Gene count identical at 2,784. Because tags "
            "are part of the bed-content digest, this makes every bed built before 2026-08-30 "
            "tagger_version=1 and not cross-comparable with v2 beds."
        ),
    },
    {
        "id": "g:2026-08-30-v091-integration",
        "date": "2026-08-30",
        "change": "v0.9.0 -> v0.9.1 shipped defaults (wave-1 rank flip carried into the release)",
        "bed_id": "enronqa_v2",
        "delivered_before": 0.694,
        "delivered_after": 0.820,
        "paired": "+66/-3",
        "pr": None,
        "receipt": "mirror/benchmarks/dogfood/receipts/sweep_v091_gate_2026-08-30.json",
        "notes": (
            "The release gate, all_pass true, decision metric delivered_gold_rate. Other cells in "
            "the same receipt: enronqa_padded 0.702 -> 0.776 (+41/-4), erb_100k 0.6099 -> 0.6312 "
            "(+7/-4), erb_829k 0.5553 -> 0.6298 (+0.0745) which reproduces the frozen wave-1 arm "
            "exactly (reproduce_delta_vs_wave1 = 0.0). Integration commit e6dba22."
        ),
    },
]


# ---------------------------------------------------------------- missing

MISSING = [
    {
        "receipt": "benchmarks/dogfood/erb/receipts/phrase_reach_2026-09-01.json",
        "named_in": "task brief; the finding it carries is summarised in research-inbox/2026-09-01-phase2-handoff.md",
        "note": "ERB Phase-1 phrase/NEAR reachability probe. No file of this name anywhere in the clone; the mirror is pinned to a commit that predates the Phase-1 commit 3ad934c.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/doc_union_oracle_2026-09-01.json",
        "named_in": "task brief; finding summarised in research-inbox/2026-09-01-phase2-handoff.md",
        "note": "ERB Phase-1 doc-union oracle probe. Not in the mirror or untracked/.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/scope_verbosity_2026-09-01.json",
        "named_in": "basis_receipts of untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
        "note": "ERB Phase-1 probe P3. The verification receipt reproduces it bit-identically apart from git_sha and wall_s, but the probe receipt itself is not archived.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/atcap_confound_2026-09-01.json",
        "named_in": "basis_receipts of untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
        "note": "ERB Phase-1 probe P5. Not archived.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/generator_leakage_2026-09-01.json",
        "named_in": "task brief",
        "note": "ERB Phase-1 generator-leakage probe. No file of this name in the clone and no research-inbox document names it.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/bucket_ledger_2026-09-01.json",
        "named_in": "basis_receipts of untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json",
        "note": "ERB Phase-1 probe P0. Not archived; the verification receipt reproduces its buckets from the raw mine.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/interloper_mine_erb947k_2026-08-31.json",
        "named_in": "basis_receipts of untracked/erb-phase2-tooling/verify_p0p3p5_2026-09-01.json; research-inbox/2026-09-01-architecture-hunt-prompt.md",
        "note": "The interloper campaign's per-miss delivered slates. Also missing: benchmarks/dogfood/interloper_taxonomy_wave{1,2}_2026-08-31.json and docs/benchmarks/2026-08-31-interloper-what-wins.md. The derived analysis research-inbox/2026-08-31-basic-miss-taxonomy.{md,json} IS in the clone and is recorded as a measurement.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/dense_ceiling_probe_829k.json",
        "named_in": "research-inbox/2026-09-01-architecture-hunt-prompt.md (killed list)",
        "note": "Dense-ceiling probe. Only the headline survives in prose (4/86 semantic at k=12, median dense rank 3,020); the exact filename is inferred from the name used in that list.",
    },
    {
        "receipt": "benchmarks/dogfood/enronqa/receipts/ladder_enronqa_native_baseline_2026-08-29.json",
        "named_in": "BASELINES.md row 2026-08-29-enronqa-native-baseline",
        "note": "The EnronQA native baseline and paraphrase-crater receipt. Its headline numbers are quoted in the BASELINES row and recorded here from that row; the file, its embedded paired_analysis and the whole benchmarks/dogfood/enronqa/ tree are absent from the mirror.",
    },
    {
        "receipt": "benchmarks/dogfood/enronqa/receipts/ladder_enronqa_v2_*_2026-08-30.json and benchmarks/dogfood/enronqa_padded/receipts/ladder_enronqa_padded_*_2026-08-30.json",
        "named_in": "BASELINES.md row 2026-08-30-v091-gate-sweep",
        "note": "Per-arm EnronQA ladders behind the v0.9.1 gate. The rolled-up sweep receipt sweep_v091_gate_2026-08-30.json IS mirrored and is the source used here.",
    },
    {
        "receipt": "benchmarks/dogfood/enronqa/receipts/ladder_enronqa_v2c_*_2026-08-30.json",
        "named_in": "BASELINES.md row 2026-08-30-entity-hub-cutoff-retrieval-ab",
        "note": "Per-arm ladders behind the entity-hub-cutoff null. The rolled-up A/B receipt is mirrored.",
    },
    {
        "receipt": "benchmarks/dogfood/muloc/receipts/ladder_muloc_budget14000_2026-08-31.json",
        "named_in": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
        "note": "MULocBench budget-14000 null. No MULocBench receipt of any kind is in the clone, so neither the baseline nor the null carries a rate here.",
    },
    {
        "receipt": "MULocBench baseline receipt (filename not stated in any archived source)",
        "named_in": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
        "note": "The synthesis cites a 226-query delivered_count=6 cohort but names no baseline receipt.",
    },
    {
        "receipt": "LoCoMo and LoCoMo+observations three-way receipts (filenames not stated in any archived source)",
        "named_in": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md; research-inbox/2026-08-31-plan-red-team.md (semantic-portfolio-lane doc, worktree vigilant-wu-5416d6)",
        "note": "Only the cohort line survives (cognitive class n=401, 3 hits). The three-way comparison itself is not archived.",
    },
    {
        "receipt": "FinanceBench baseline receipt (filename not stated in any archived source)",
        "named_in": "research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md",
        "note": "Called the 'FinanceBench baseline blackout'; only the metrics-class cohort line survives (n=50, 0 hits).",
    },
    {
        "receipt": "W2.2 eps_band_coverage arm receipt (filename not stated in any archived source)",
        "named_in": "research-inbox/2026-09-01-architecture-hunt-prompt.md killed list; research-inbox/2026-08-31-SYNTHESIS-representation-campaign.md ladder item 5",
        "note": "The 470-needle W2.2 arm was in flight on 2026-08-31 and appears as killed on 2026-09-01. No receipt, no numbers.",
    },
    {
        "receipt": "947k min_delivered_docs floor width curve (12 vs 6 A/B)",
        "named_in": "task brief",
        "note": "Only the floor-12 arm (ladder_v09x_w24_min_delivered_2026-08-28.json) and the cross-corpus floor cells inside sweep_v091_gate_2026-08-30.json exist here. No multi-width curve receipt is in the clone; the basic-miss taxonomy records width6_queries=68 and width12_queries=107 as an observation, not as an A/B.",
    },
    {
        "receipt": "benchmarks/dogfood/erb/receipts/pool_depth_capture_2026-09-01.sqlite and pool_depth_ck_2026-09-01/cache/deep1000.jsonl",
        "named_in": "research-inbox/2026-09-01-phase2-handoff.md",
        "note": "The interrupted A1 pool-depth capture. The tooling and the smoke JSONs were copied into untracked/erb-phase2-tooling/, but the sqlite capture and the 114-record checkpoint cache were not. The handoff warns that the smoke files' 'VERDICT KILL' lines are 2-4 needle smokes and must not be read as results, so no kill is recorded from them.",
    },
    {
        "receipt": "benchmarks/scbench/campaigns/2026-08-08-codex-pilot/ and 2026-08-11-codex-terra/",
        "named_in": "BASELINES.md rows 2026-08-08-codex-pilot and 2026-08-11-codex-terra",
        "note": "The SCBench campaign trees have rows in the ledger but no mirrored receipts, so no SCBench measurement is recorded.",
    },
]


# ---------------------------------------------------------------- assembly


def main() -> None:
    parse_erb_ladders()
    parse_dogfood_data()
    parse_sike_bedsweep()
    parse_snow()
    parse_v091_gate()
    parse_entity_hub_ab()
    parse_sema_ingest_ab()
    parse_tagger_v2()
    add_curated_measurements()

    measurements = sorted(MEASUREMENTS, key=lambda m: (m["date"] or "", m["id"]))
    ledger = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "source_commit": SOURCE_COMMIT,
        "schema_notes": {
            "paths": "receipt paths are relative to the clone root; mirrored receipts start with mirror/. BASELINES.md cites the same files without that prefix.",
            "basis": "delivered = post-budget delivery slice (delivered_gold_rate). final = final ranked order handed downstream (final_recall_at_12). map = candidate-pool / score-map recall (recall_at_12). delivered and final are different metrics and are never merged.",
            "shipped_default": "computed mechanically for ladder receipts: true only when the arm is named baseline, runs the repo cymatix.toml, and overrides no knobs. An arm that merely re-pins the shipped value in its own config TOML reads false.",
            "nulls": "a null field means the source does not state that number. Nothing is estimated or back-filled.",
        },
        "beds": sorted(BEDS, key=lambda b: (b["family"], b["id"])),
        "measurements": measurements,
        "kills": sorted(KILLS, key=lambda k: (k["date"], k["id"])),
        "graduations": sorted(GRADUATIONS, key=lambda g: (g["date"], g["id"])),
        "missing": MISSING,
        "unparsed": sorted(UNPARSED, key=lambda u: u["receipt"]),
        "counts": {
            "beds": len(BEDS),
            "measurements": len(measurements),
            "kills": len(KILLS),
            "graduations": len(GRADUATIONS),
            "missing": len(MISSING),
            "unparsed": len(UNPARSED),
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(ledger, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")

    print("wrote %s" % OUT)
    for key, val in ledger["counts"].items():
        print("  %-14s %d" % (key, val))
    for entry in ledger["unparsed"]:
        print("  UNPARSED %s :: %s" % (entry["receipt"], entry["reason"]))


if __name__ == "__main__":
    main()
