# untracked/benchmarks/dogfood

Plain file copies of interloper-mining dumps that the code repo deliberately left untracked.

## LoCoMo pair, wave-1 interloper campaign (2026-08-31)

| file | bytes | sha256 |
|---|---:|---|
| `locomo/receipts/interloper_mine_locomo_2026-08-31.json` | 15433874 | `edc76360a36ea15be4a6460f88b59eabac2be499d88b5ecf15403b0ceae2c628` |
| `locomo_obs/receipts/interloper_mine_locomo_obs_2026-08-31.json` | 13413969 | `eed5c942ea2ab6c3fd180de98071d2d6d23e860608d6ac1f093cdb6938993be8` |

- source: worktree `F:/Projects/cymatix-context/.claude/worktrees/vigilant-wu-5416d6`
  (branch `bench/semantic-portfolio` @ `b5eb803d3f634b225185186bf8f3539105c3e194`, an ancestor of
  `origin/beta`), where both files were untracked (`??`), never gitignored, never committed.
- generator: `benchmarks/dogfood/mine_interlopers.py` (tracked on beta) against beds
  `F:/tmp/locomo_bed/locomo.db` and `F:/tmp/locomo_obs_bed/locomo_obs.db`, basis receipts
  `ladder_locomo_baseline_2026-08-31.json` / `ladder_locomo_obs_2026-08-31.json` (tracked on beta), k=12.
- content: locomo 1,344 misses mined, rank_match 1344/1344, replay_errors 0, wall 37.7 s;
  locomo_obs 1,144 misses, rank_match 1144/1144, replay_errors 0, wall 45.4 s.
- consumers on beta: `benchmarks/dogfood/interloper_taxonomy_wave1_2026-08-31.json` (LoCoMo rows) and
  `docs/benchmarks/2026-08-31-interloper-what-wins.md` (per-bed table), whose line 9-10 records the pair
  as "untracked, 15MB/13MB, regenerable in <1 min". The other five beds' mine dumps are tracked on beta.
- caveat: the locomo bed's mtime (Aug 31 22:11) is later than the dump (18:45) because the hit-slate probe
  touched the bed after mining, so a regenerated dump may not be byte-identical; these copies are the ones
  the taxonomy consumed.
