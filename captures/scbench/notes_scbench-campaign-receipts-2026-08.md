# SCBench Codex/Cymatix campaign pair receipts (Luna pilot + Terra, August 2026)

Disk-only pair receipts of the SCBench Codex/Cymatix paired regression-resistance A/B harness (Cymatix-Context branch `codex/scbench-cymatix-ab`, worktree head `9312cde85e88`). These paths are gitignored on the branch and existed in no git ref; the committed part of the campaigns (manifests, READMEs, qualification receipts, Luna analysis) is mirrored under `mirror-branches/codex__scbench-cymatix-ab/`.

Each asset is a tar (entries rooted at `benchmarks/scbench/campaigns/<campaign>/`) compressed with zstandard level 12. Verify the download against `sha256_zst`, decompress with python `zstandard` (`ZstdDecompressor().copy_stream`), verify `sha256_tar`, then extract. Sidecar `cymatix.genome.db` files were WAL-checkpointed on the copy and their `-wal`/`-shm` sidecars dropped; per-db source and archived sha256 are in `captures/scbench/MANIFEST.json`.

| label | asset | campaign | source files | archived files | tar MB | zst MB | ratio | dropped sidecars |
|---|---|---|---:|---:|---:|---:|---:|---:|
| scbench-luna-pilot-2026-08-08 | `scbench-luna-pilot-2026-08-08.tar.zst` | `2026-08-08-codex-pilot` | 5071 | 5039 | 195.2 | 13.4 | x14.52 | 32 (53.1 MB) |
| scbench-terra-2026-08-11 | `scbench-terra-2026-08-11.tar.zst` | `2026-08-11-codex-terra` | 4973 | 4941 | 191.4 | 13.4 | x14.25 | 32 (55.3 MB) |

## Verdicts

- `2026-08-08-codex-pilot` (frozen tag `bench/scbench-luna-2026-08-08`): Luna pilot: NOT graduated (4/8 predeclared gates fail, issue #359 decision STOP); analysis-v2 (committed on the branch) no_detectable_difference, safety gates pass
- `2026-08-11-codex-terra` (frozen tag `bench/scbench-terra-2026-08-11`): Terra v2: no_detectable_difference, all 7 safety gates pass (head-to-head cymatix 18 / control 24 / tied 22; input-token ratio 1.13; elapsed 1.08)

## sha256

- `scbench-luna-pilot-2026-08-08.tar.zst`  zst 4f21ead8c283499b2f3ce096d054ef72b427443ea5eb4e723bbd014227f349ac  tar ec62da9fc6d39713c5ab47853332b1ccb6ca57e2afd2cdecf694350cc79d219c
- `scbench-terra-2026-08-11.tar.zst`  zst 1a0556225c5183daca11ff5c78d5a5d6d27c3d2acee6eb30405332ac250ceec1  tar dd1c859b761e945566da5c81e004da6bd59065cfba41ff2e044c48f6b4999215

## Privacy

Pair receipts include Codex CLI stdout/stderr, agent run logs, workspace snapshots of the SCBench problems, and the per-pair sidecar knowledge store. They were produced by a benchmark harness against synthetic SCBench problems, not by the transparent proxy, but nothing here has been content-scanned. The repository stays private until an owner review clears it.
