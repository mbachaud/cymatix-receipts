# Bench and dogfood beds (May to July 2026)

Compressed SQLite knowledge stores (`VACUUM INTO` copies of the originals, zstandard level 12). Verify each download against `sha256_zst` in `beds/MANIFEST.json`, then decompress with python `zstandard` (`ZstdDecompressor().copy_stream`) and verify `sha256_raw`.

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

## sha256 (zst)

- `genome-bench-2026-05-08-frozen.db.zst`  d22b54b36f6a06097792a4233604fd433d17c13fd3921aa6ecaf3de1f1e40c8a
- `bench-matrix-small.db.zst`  f32accf29e824410dc4d22dec989b707ad89875009c346dd696eca379838c7f3
- `enterprise-rag-smoke.db.zst`  8ea12cbf214d97e2a1ab9b1f8ec56ebf6d8a7d6cc5d770b89dd89af99ddfc047
- `genomes-main-current.db.zst`  6e0bd7f039c93da0d6e082687120e1690a2f2524c46d1f4aaceba093c3d0ef0a
- `dogfood-bed.db.zst`  50601d1b5d0fa7cc054f9c4e921517c8ed0642fc153dfd55856b4083c204f424
- `assetops-bed.db.zst`  0bc370e2c97b5163125178169b3ecbe3dd2573347b8cbce8b9f74d258bbba84f
- `taggerdogfood-e2b.db.zst`  01fc9fb6b4a9bcb1078bf08cfa501ffe434dbe1286f37e67116cdf0136269762
- `taggerdogfood-cpu.db.zst`  e96c7ef88f54b0bf42ffe4943db70ab62ba8d0656521a1c3253dc53431eccfd6

## Privacy

Privacy audit: a name-based heuristic (content_type / source / origin columns, exchange-like table names) found no persisted query/response exchanges; the only flagged rows are hitl_events records (human-in-the-loop pause events, counts in the manifest). These schemas carry no content_type column, so the audit is not a content scan. The repository stays private until an owner review clears it.
