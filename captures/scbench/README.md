# SCBench campaign receipts

Release assets holding the gitignored pair receipts of the two SCBench Codex/Cymatix A/B campaigns (Luna pilot 2026-08-08, Terra 2026-08-11). Source: worktree `F:\Projects\cymatix-context\.claude\worktrees\scbench-codex-ab` at `9312cde85e88` (branch `codex/scbench-cymatix-ab`); no git ref anywhere held these files. `MANIFEST.json` carries sizes, both hashes, asset URLs and the per-sidecar checkpoint records; the release notes are in `notes_scbench-campaign-receipts-2026-08.md`.

Release: https://github.com/mbachaud/cymatix-receipts/releases/tag/scbench-campaign-receipts-2026-08

| label | asset | campaign | source files | archived files | tar MB | zst MB | ratio | dropped sidecars |
|---|---|---|---:|---:|---:|---:|---:|---:|
| scbench-luna-pilot-2026-08-08 | `scbench-luna-pilot-2026-08-08.tar.zst` | `2026-08-08-codex-pilot` | 5071 | 5039 | 195.2 | 13.4 | x14.52 | 32 (53.1 MB) |
| scbench-terra-2026-08-11 | `scbench-terra-2026-08-11.tar.zst` | `2026-08-11-codex-terra` | 4973 | 4941 | 191.4 | 13.4 | x14.25 | 32 (55.3 MB) |

## Restore

```python
import hashlib, tarfile, zstandard as zstd
src, dst = 'scbench-terra-2026-08-11.tar.zst', 'scbench-terra-2026-08-11.tar'
with open(src, 'rb') as fi, open(dst, 'wb') as fo:
    zstd.ZstdDecompressor().copy_stream(fi, fo)
print(hashlib.sha256(open(dst, 'rb').read()).hexdigest())  # compare with sha256_tar
tarfile.open(dst).extractall('<checkout of codex/scbench-cymatix-ab>', filter='data')
```

## Privacy

Pair receipts include Codex CLI stdout/stderr, agent run logs, workspace snapshots of the SCBench problems, and the per-pair sidecar knowledge store. They were produced by a benchmark harness against synthetic SCBench problems, not by the transparent proxy, but nothing here has been content-scanned. The repository stays private until an owner review clears it.

Generated 2026-09-02T05:52:15.352820+00:00 by `scripts/salvage_scbench.py`.
