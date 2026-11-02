# BEIR 20-bed sweep on a Linux cloud VM (2026-11-02)

Every BEIR bed from the 2026-10-11 traced sweep (`../traced_sweep_2026-10-11/`),
rebuilt from the public UKP zips and scored on a Linux cloud VM. This checks
whether the Windows BEIR receipts reproduce on another platform at a later commit.

**Not a ledger row.** Nothing in this folder is citable until it has a row in
`docs/benchmarks/BASELINES.md`. The comparison below crosses platform and commit
at once (see "What differs"), so it is a cross-platform check, not a paired A/B.

## Conditions

| | this run | reference (traced_sweep_2026-10-11) |
|---|---|---|
| engine | `bd3c541f` = beta `091dab94` + PR #534 (resolver path fix only) | `da55e457` |
| host | Linux 6.18, 4 vCPU, 15 GB RAM, no GPU, Python 3.13.18 | Windows 11, Python 3.14.3 |
| config | shipped `cymatix.toml` | shipped `cymatix.toml` |
| builder | `build_fixture_matrix.py --parallel --workers 4` (ingest_c=4), `CYMATIX_BFM_HUB_CUTOFF=200`, `CYMATIX_BFM_DENSE_BACKFILL=0`, **`CYMATIX_BFM_SPLADE=0`** | same, SPLADE written |
| ladder | `ablation_ladder.py --cover-index off --limit 0 --k 12 --arms baseline --per-query --rank-dump 200` | same |
| env | `PYTHONHASHSEED=0 PYTHONUTF8=1 CYMATIX_DISABLE_LEARN=1 CYMATIX_SQLITE_CACHE_SIZE=-12582912 CYMATIX_COVER_INDEX_AUTOBUILD=0`, encoder and config env unset | same |
| min_file_bytes | 1 (current profile) | 1, except round-1 beds (50) |
| cold-bed gate | **skipped**, so latency is warm-cache | 1 h |

`run_beir_linux.py` is the driver: a Linux port of
`benchmarks/dogfood/sweeps/run_beir_round1.py` that patches only paths, plus the
SPLADE, floor and cleanup switches. `compare.py` and the `package.py` logic produced
`TABLE.md` and `SUMMARY.json`. The emitted needles, gold_paths and gold_grades
were byte-identical to the committed `benchmarks/dogfood/beir_scifact/` files
(checked on scifact).

CQADupStack `queries.jsonl` was cut down to the test-qrel ids and to the `_id` and
`text` fields to fit the VM disk. The emitter reads nothing else, so the emitted
needles are unchanged.

### SPLADE-off is retrieval-inert (receipted)

`beir_scifact/splade_on/` is the same bed built with SPLADE. All 300 rank lists
are identical to the SPLADE-off bed, and its nDCG@10 is the same 0.4942. The
SPLADE-off build took 50 s against 1,290 s with SPLADE, which is why every other
bed was built SPLADE-off. The equivalence was shown on scifact only.

## Results (nDCG@10, BEIR-comparable basis; per-query = needles whose nDCG@10 moved)

| bed | arm | ref nDCG@10 | VM nDCG@10 | Δ | R@100 ref / VM | per-query nDCG +/− |
|---|---|---|---|---|---|---|
| beir_scifact | baseline | 0.4942 | 0.4942 | +0.0000 | 0.8281 / 0.8281 | +0/−0 of 300 |
| beir_scifact | splade_on | 0.4942 | 0.4942 | +0.0000 | 0.8281 / 0.8281 | +0/−0 of 300 |
| beir_nfcorpus | baseline | 0.2830 | 0.2830 | +0.0000 | 0.2083 / 0.2083 | +1/−0 of 323 |
| beir_arguana | baseline | 0.2701 | 0.2700 | -0.0001 | 0.9101 / 0.9094 | +20/−23 of 1401 |
| beir_arguana | floor50 | 0.2701 | 0.2700 | -0.0001 | 0.9101 / 0.9094 | +20/−23 of 1401 |
| beir_fiqa | baseline | 0.1649 | 0.1648 | -0.0001 | 0.4031 / 0.4025 | +3/−4 of 648 |
| beir_fiqa | floor50 | 0.1649 | 0.1647 | -0.0002 | 0.4031 / 0.4025 | +3/−4 of 648 |
| beir_scidocs | baseline | 0.1133 | 0.1129 | -0.0004 | 0.2551 / 0.2554 | +6/−7 of 1000 |
| beir_scidocs | floor50 | 0.1133 | 0.1126 | -0.0007 | 0.2551 / 0.2542 | +3/−6 of 1000 |
| beir_trec_covid | baseline | 0.4995 | 0.5003 | +0.0008 | 0.0550 / 0.0551 | +1/−0 of 50 |
| beir_webis_touche2020 | baseline | 0.2751 | 0.2790 | +0.0039 | 0.4052 / 0.4056 | +5/−1 of 49 |
| beir_quora | baseline | 0.5499 | 0.5487 | -0.0012 | 0.9068 / 0.9066 | +129/−254 of 10000 |
| CQADupStack mean (12 forums) | baseline | 0.1986 | 0.1982 | -0.0004 | — | +40/−71 of 13145 |

`TABLE.md` has the per-forum CQADupStack rows. Over all 20 baseline beds,
205 needles improved and 360 got worse out of 26,916.

## Reading

- scifact reproduces exactly across platform and commit. nfcorpus moves on one
  needle.
- Every other bed is within ±0.004 nDCG@10. That includes touche2020 (+0.0039,
  but n=49) and quora (−0.0012, +129/−254). The per-needle moves lean negative:
  360 worse against 205 better.
- **The 50-byte floor does not explain the churn.** The round-1 reference beds were
  built under the old 50-byte floor (arguana +1, scidocs +108, fiqa +158 short docs
  now admitted). Rebuilding those three at floor 50 (`floor50/`) left the churn in
  place.
- **Cause not isolated.** Platform (file enumeration order, Python 3.13 vs 3.14,
  sqlite) and the code changes between `da55e457` and `091dab94` are confounded
  here. To separate them, a Windows run at `bd3c541f`, or a Linux run at
  `da55e457`, would be needed.

## Layout

`<bed>/` holds the ladder receipt, the nDCG receipt, the resolved needles and gold,
`build_log_tail.txt` (gene and file counts) and `bed_manifest.json` where the bed
survived. Beds and corpora after round 1 were deleted once scored, to fit the VM
disk, so those beds have only the log tail. `<bed>/floor50/` and
`<bed>/splade_on/` hold the variant arms.
