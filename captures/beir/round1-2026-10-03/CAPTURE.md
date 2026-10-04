# BEIR round 1 ladder receipts (2026-10-03)

Issue: mbachaud/Cymatix-Context#482. Ten ablation-ladder receipts with
`--per-query --rank-dump 200` (2-8 MB each, too large to commit to the code
repository per arm): five BEIR beds x two arms.

| bed | n | baseline (shipped `cymatix.toml`) | diagnostic (`tag_lanes_muted.toml`) |
|---|---:|---|---|
| beir_scifact | 300 | `ladder_beir_scifact_seed0_2026-10-03.json` | `ladder_beir_scifact_diag_tag_lanes_muted_seed0_2026-10-03.json` |
| beir_nfcorpus | 323 | `ladder_beir_nfcorpus_seed0_2026-10-03.json` | `ladder_beir_nfcorpus_diag_tag_lanes_muted_seed0_2026-10-03.json` |
| beir_arguana | 1,401 | `ladder_beir_arguana_seed0_2026-10-03.json` | `ladder_beir_arguana_diag_tag_lanes_muted_seed0_2026-10-03.json` |
| beir_scidocs | 1,000 | `ladder_beir_scidocs_seed0_2026-10-03.json` | `ladder_beir_scidocs_diag_tag_lanes_muted_seed0_2026-10-03.json` |
| beir_fiqa | 648 | `ladder_beir_fiqa_seed0_2026-10-03.json` | `ladder_beir_fiqa_diag_tag_lanes_muted_seed0_2026-10-03.json` |

Provenance:

- Code: Cymatix-Context branch `claude/benchmarking-expansion-enhancement-6f26b6`;
  baseline receipts carry `git_sha` 021b3403, diagnostic receipts f332914d
  (each receipt's own `git_sha` field is authoritative).
- Beds: `F:/tmp/beir_<name>_bed/beir_<name>.db`, built by
  `scripts/build_fixture_matrix.py --parallel --workers 4` (ingest_c=4),
  tagger v2, `CYMATIX_BFM_HUB_CUTOFF=200`, no dense backfill, 50-byte size floor
  (built before the per-profile `min_file_bytes` override existed).
- Run: k=12, `PYTHONHASHSEED=0`, `CYMATIX_DISABLE_LEARN=1`, encoder unset,
  1 h cold gate, runner `benchmarks/dogfood/sweeps/run_beir_round1.py`.
- Scored by `benchmarks/dogfood/beir/beir_ndcg.py`; the score receipts
  (`beir_ndcg_*.json`) are committed in the code repository next to where these
  ladder receipts were written.
- sha256 of every file here is pinned in the code repository at
  `benchmarks/dogfood/beir/ladder_receipts_round1-2026-10-03.json`.

Citable only once the round has a row in `docs/benchmarks/BASELINES.md`.
