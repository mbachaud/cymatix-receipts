# Archived beds

Knowledge-store snapshots archived as GitHub Release assets of this repository. Each asset is a `VACUUM INTO` copy of the source database (WAL checkpointed on the copy, sources never modified), compressed with zstandard level 12 and round-trip verified. `MANIFEST.json` carries both hashes, row counts, table lists, and the privacy heuristic result per bed.

## Release `early-beds-2026-04`: Early knowledge-store snapshots (Helix era, April 2026)

https://github.com/mbachaud/cymatix-receipts/releases/tag/early-beds-2026-04

| label | asset | raw MB | zst MB | ratio | docs | privacy rows | source |
|---|---|---:|---:|---:|---:|---:|---|
| helix-cache-genome | `helix-cache-genome.db.zst` | 248.9 | 49.3 | x5.05 | 7737 | 0 | `E:\helix-cache\genome.db` |
| genome-bench-2026-04-10 | `genome-bench-2026-04-10.db.zst` | 549.4 | 173.8 | x3.16 | 7313 | 0 | `E:\Helix-backup blobs\genome-bench-2026-04-10.db` |
| genome-bench-2026-04-14 | `genome-bench-2026-04-14.db.zst` | 798.7 | 156.3 | x5.11 | 18254 | 0 | `E:\Helix-backup blobs\genome-bench-2026-04-14.db` |
| genome-2026-04-15 | `genome-2026-04-15.db.zst` | 825.7 | 161.9 | x5.1 | 19692 | 0 | `E:\Helix-backup blobs\genome.db` |
| genomes-main-2026-04-21 | `genomes-main-2026-04-21.db.zst` | 258.9 | 51.5 | x5.03 | 7982 | 3 | `E:\Helix-backup blobs\helix-context-2026-04-21\genomes-main-genome.db` |
| genome-bench-organic | `genome-bench-organic.db.zst` | 298.4 | 60.0 | x4.98 | 8872 | 0 | `E:\Helix-backup blobs\helix-context-2026-04-21\genome_bench_organic.db` |
| genome-cpu | `genome-cpu.db.zst` | 275.3 | 60.8 | x4.53 | 8021 | 0 | `E:\Helix-backup blobs\helix-context-2026-04-21\genome_cpu.db` |
| genome-llm-backup | `genome-llm-backup.db.zst` | 57.2 | 19.1 | x3.0 | 3501 | 0 | `E:\Helix-backup blobs\helix-context-2026-04-21\genome_llm_backup.db` |
| genome-bench-helix | `genome-bench-helix.db.zst` | 22.1 | 5.2 | x4.26 | 687 | 0 | `E:\Helix-backup blobs\helix-context-2026-04-21\genome_bench_helix.db` |

## Release `bench-beds-2026-05-to-07`: Bench and dogfood beds (May to July 2026)

https://github.com/mbachaud/cymatix-receipts/releases/tag/bench-beds-2026-05-to-07

| label | asset | raw MB | zst MB | ratio | docs | privacy rows | source |
|---|---|---:|---:|---:|---:|---:|---|
| genome-bench-2026-05-08-frozen | `genome-bench-2026-05-08-frozen.db.zst` | 1179.5 | 183.4 | x6.43 | 18936 | 8 | `F:\Projects\cymatix-context\benchmarks\genome-bench-2026-05-08-frozen.db` |
| bench-matrix-small | `bench-matrix-small.db.zst` | 45.2 | 13.3 | x3.39 | 1238 | 0 | `F:\Projects\helix-context\genomes\bench\matrix\small.db` |
| enterprise-rag-smoke | `enterprise-rag-smoke.db.zst` | 138.5 | 30.7 | x4.51 | 2181 | 0 | `F:\Projects\helix-context\genomes\bench\enterprise_rag_smoke.db` |
| genomes-main-current | `genomes-main-current.db.zst` | 12.9 | 4.8 | x2.66 | 757 | 1 | `F:\Projects\cymatix-context\genomes\main\genome.db` |
| dogfood-bed | `dogfood-bed.db.zst` | 261.5 | 67.8 | x3.85 | 6272 | 2 | `F:\Projects\cymatix-context\genomes\dogfood\genome.db` |
| assetops-bed | `assetops-bed.db.zst` | 198.5 | 57.4 | x3.46 | 5636 | 0 | `F:\Projects\cymatix-context\genomes\assetops-bed\genome.db` |
| taggerdogfood-e2b | `taggerdogfood-e2b.db.zst` | 143.4 | 49.0 | x2.93 | 5693 | 0 | `F:\Projects\cymatix-context\genomes\taggerdogfood\genome.db` |
| taggerdogfood-cpu | `taggerdogfood-cpu.db.zst` | 215.2 | 59.0 | x3.65 | 6276 | 0 | `F:\Projects\cymatix-context\genomes\taggerdogfood_cpu\genome.db` |

## Restore

```python
import hashlib, zstandard as zstd
src, dst = 'dogfood-bed.db.zst', 'dogfood-bed.db'
with open(src, 'rb') as fi, open(dst, 'wb') as fo:
    zstd.ZstdDecompressor().copy_stream(fi, fo)
print(hashlib.sha256(open(dst, 'rb').read()).hexdigest())  # compare with sha256_raw
```

## Not archived

- E:/Helix-backup blobs/genome-bench-2026-04-10.db.SAFETY_COPY (byte-duplicate of genome-bench-2026-04-10)
- E:/Helix-backup blobs/genome-bench-{A3,fresh,N1000,N50,PKI,PKI2}.db (mid-experiment variants of the 2026-04-12/13 bench bed)
- E:/Helix-backup blobs/helix-context-2026-04-21/genome.db (+wal) and genome_2026-04-15_pre_fresh.db (near-duplicates of genome-2026-04-15)
- E:/Helix-backup blobs/helix-context-2026-04-21/genome.db.pre-*.bak (pre-compact / pre-backfill / pre-reingest safety copies)
- F:/Projects/helix-context/genomes/bench/{matrix,sike_beds}/* larger than 500 MB (matrix medium/large/xl, enterprise_rag_10k/50k, sike beds): live bench beds, 165 GB, stay in place

## Privacy

Privacy audit: a name-based heuristic (content_type / source / origin columns, exchange-like table names) found no persisted query/response exchanges; the only flagged rows are hitl_events records (human-in-the-loop pause events, counts in the manifest). These schemas carry no content_type column, so the audit is not a content scan. The repository stays private until an owner review clears it.

Generated 2026-09-01T21:51:09.361826+00:00 by `publish_beds.py`.
