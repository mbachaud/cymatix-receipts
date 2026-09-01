# Early knowledge-store snapshots (Helix era, April 2026)

Compressed SQLite knowledge stores (`VACUUM INTO` copies of the originals, zstandard level 12). Verify each download against `sha256_zst` in `beds/MANIFEST.json`, then decompress with python `zstandard` (`ZstdDecompressor().copy_stream`) and verify `sha256_raw`.

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

## sha256 (zst)

- `helix-cache-genome.db.zst`  bae111a7c3a4687d8570f70c13a4b8a293d5f86748c2a309c441520889a04505
- `genome-bench-2026-04-10.db.zst`  5341861e58cd2b3739c1a4d7a848a9e7ebcf4df88d56199a7dd7e8ab23e2021d
- `genome-bench-2026-04-14.db.zst`  9f6f356c29ff13313b8d386b6e128fa2ff3be269e82a1a42494cb262a1a1b975
- `genome-2026-04-15.db.zst`  416337a19f11b3d4cacaa3e920cb5e2e91e9be69f4d4fb412a95964de22a014c
- `genomes-main-2026-04-21.db.zst`  4cadf14091c8adec65849502eecad70bd731e56121c3bc2be8eb237795038f28
- `genome-bench-organic.db.zst`  70c031ceb6c9b945b6bab81417a3eca0a5bb484228e0fad032a8107f1b1dcedd
- `genome-cpu.db.zst`  6c25e8305691cd134d5392c90c8c2d4a5adc787d502823aa641d1cd02ab62fd0
- `genome-llm-backup.db.zst`  4b093a607415027c6601810a1c6086ed5f8608989de1c3bb43a4a1d5c34eada7
- `genome-bench-helix.db.zst`  806ba4979dba6e557257bbeb96e8ecbe4c390a0d2793707ab23d6de2e8dfddb0

## Privacy

Privacy audit: a name-based heuristic (content_type / source / origin columns, exchange-like table names) found no persisted query/response exchanges; the only flagged rows are hitl_events records (human-in-the-loop pause events, counts in the manifest). These schemas carry no content_type column, so the audit is not a content scan. The repository stays private until an owner review clears it.
