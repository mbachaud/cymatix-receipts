# Phase 2 — handoff (stopped mid-flight 2026-09-01 14:14 PDT)

Stopped deliberately for a desktop-client update, not by failure. Everything below is on disk.

## Where things stand

**Campaign question:** lift ERB 947k `delivered_gold_rate` from .6681 (314/470) to .80 (+62 needles),
lexical-only (FTS5 + tags + synonyms, RRF rrf_k=20, k=12).

### The reframe that came out of Phase 1

**109 of 156 misses (69.9%) have gold nowhere in the observed score map; only 47 have it anywhere.**
So a *perfect* re-ranker over the current pool caps at **(314+47)/470 = 0.768 — below target.**
The +62 must come from **admission or indexing, not ordering.** Every lever the external evidence pass
ranked was an ordering/aggregation lever.

### Killed in Phase 1 (receipts on disk, committed at `3ad934c`)

| Lever | Why it died |
|---|---|
| Exact-phrase + `NEAR` lane fused into RRF | **Discrimination, not reachability.** Reach is fine (31/37 basic pool-absent reachable; 94.2% of all misses with the DF cap lifted). But fire rate is **0.9126 on standardised hits vs 0.7372 on misses** — inverted, negative at every k, in all 7 strata. Bootstrap 95% CI [−0.2616, −0.0855], P(delta ≥ +0.10) = 0.0000. DF ≤ 12 "seat-forcing" phrases exist for 46.2% of hits vs 18.6% of misses. |
| Phrase as a re-ranking *feature* | Gold out-phrases the best already-delivered chunk on only **29/156 (18.6%)**; ties 78, loses 49. And gold chunks are 17% shorter on a length-monotone statistic, so the control is generous to gold. |
| Doc-rollup / chunk aggregation to `source_id` | UNION doc rank-1 **17/156 vs analytic random 15.6** — indistinguishable from a shuffle. A realizable rollup over the real score pool nets **one** new rescue. Corpus is 1.895 chunks/doc, 78.6% of docs ≤2 chunks (PARM CaseLaw, where this *hurt* shallow recall, had 7.5). |
| Length-normalization family (BM25 `b`, rank-time length penalty) | Died of an **absent** mechanism. Verbosity runs backwards (winner/gold/corpus avg_tf **1.541/1.571/1.691**); boilerplate fires at **0.0%**. Gold is *not* short — 47.8% of the corpus is at the 4,000-char cap, so gold's 42.9% is the base rate; the anomaly is entirely winner-side (1.80x). |

### Killed in Phase 2 (two agents, independently)

**Head-chunk monopoly — REFUTED as a presentation-order artifact.** P5's "156/156 top-1 winners are
head-or-only, p=1.1e-19" measured `sorted(candidates, key=lambda g: g.promoter.sequence_index or 0)`
at `context_manager.py:3355` — the delivered *order* is chunk-index-ascending, so seat 1 is head-or-only
with probability **exactly 1**. Delivered set is bit-identical to the score top-k (mean overlap 1.000
across 40 live replays); only order differs. In true score order it's 79.49%, and within the pool rank
carries zero head-chunk information (17.29% vs 17.47% middle share at rank 1 vs ranks 2–15).
**Addressable population: zero.**

> **Contaminant to run down:** if `delivered[0]` is sequence-ordered rather than score-ordered, then every
> statistic defined against "the rank-1 winner" may compare gold to an arbitrary chunk of the slate.
> That includes the `chunk_split` flag (65/156) and the wave-2 taxonomy's coverage duels. Nothing
> currently rests on it (the lane it justified is already dead), but the taxonomy may need a note.

Also from Phase 2 verification: **P3 CONFIRMED** (headline reproduced by an independent route).
**P0's bucket ledger and `rloss.py` are CORRECT** — the scorer that will grade every future A/B is sound.

## Banked measurements from the interrupted A1 (pool-absence forensics)

These are real and reproducible; they came from the harness's own smoke runs before the full capture.

| Measurement | Value |
|---|---|
| Shipped score-map median depth | **49** (49.5 on a second smoke) |
| `fts5_candidate_depth` at shipped defaults | 0 = auto = `max_genes_per_turn × 4` = **48** |
| Deep-capture map depth | 1000 (capture works) |
| `deep1000` p50 vs `shipped` p50 | **19,044 ms vs 18,764 ms — ratio 1.015** |
| Second smoke (opposite ordering) | shipped 25,509 ms vs deep 19,069 ms — **ratio 0.748** |
| BM25 proxy p50 | ~2,900 ms |

**The ~49-deep map against a 48-deep fetch is now measured, not inferred.** And **depth 1000 is
latency-neutral** — the agent flagged its own confound (deep ran first on a cold page cache, shipped
second warm), which means 1.015 *overstates* the cost of depth. That retires the main objection to a
candidate-depth A/B before it runs.

### ⚠ Do NOT read the "VERDICT KILL" lines in the A1 transcript as a result

Four lines read `VERDICT KILL: pool_absent gold found at depth<=1000 = 2/2 (threshold 30)`. These are
**smoke tests on 2–4 needles** (`smoke3.json`, `smoke4.json`). The harness compares a raw count against
the threshold sized for the full 109, so 2 < 30 prints KILL mechanically. On those samples gold was found
**2/2 and 3/3** with `absent_at_1000: 0`, and some sat at rank 49–200 — i.e. *beyond* the shipped cutoff.
If anything the sample leans **toward** the admission thesis. The pre-registered gate is unresolved.

## Resume path

The full capture reached **~113 of 216 targets** on the deep1000 leg before the stop. Checkpoints and all
scratch tooling were copied out of the session-scoped temp dir into the repo:

```
benchmarks/dogfood/erb/receipts/pool_depth_ck_2026-09-01/
  cache/deep1000.jsonl        <- 114 checkpoint records, resumable
  smoke{,2,3,4,5}.json        <- smoke receipts incl. the misleading VERDICT lines
  *.py                        <- probe/attack tooling from Phases 1-2
benchmarks/dogfood/erb/receipts/pool_depth_capture_2026-09-01.sqlite  (14.4 MB + WAL)
```

Workflow resume (completed agents replay from cache; A1 restarts):

```
Workflow({scriptPath: "C:\\Users\\max\\.claude\\projects\\F--Projects-cymatix-context--claude-worktrees-wave-1-semantic-ranking-5f1dab\\c81df3a0-0a0c-4160-81ee-e68db3b02372\\workflows\\scripts\\erb-phase2-admission-wf_c2129369-b92.js", resumeFromRunId: "wf_c2129369-b92"})
```

Hygiene + A3 + A5 return instantly from cache. A1 does not — an agent's result isn't cached until it
returns, so it restarts, but it can pick up the checkpoint above if pointed at it.

**The one open question A1 exists to answer:** does `pool_absent` mean gold is genuinely unretrievable,
or does it mean gold sits past rank 48 and we truncate admission there? Pre-registered gate: **KILL the
admission thesis if fewer than 30 of the 109 pool-absent misses have gold anywhere at depth 1000** — in
which case re-scope the .80 target rather than spend another wave.

## Structural facts every future arm inherits

- **ERB gold is document-complete**: 386 gold gene_ids == 386 chunks of the gold documents; 722 gold
  source_ids have zero non-gold chunks. Any "gold vs non-gold sibling" metric is an **empty set** and
  returns a tautology. Phase 1 lost a headline finding to exactly this.
- **The 61 semantic pool-absent are adversarial by construction.** Provenance traced to the upstream
  `EnterpriseRAG-Bench` checkout: basic *and* semantic generation prompts carry explicit anti-lexical
  instructions, and it landed — all 125 semantic queries cap at content-LCN 4. **No lexical lever converts
  them.** State this whenever .80 is discussed.
- **The map is ~45–49 deep, so the taxonomy's "13–100 near band" is decorative** — the real band is 13–45.
- **No index on `genes.source_id`** — sibling lookup is a full 947k scan. Build the map in one pass (~5 s).
- **Bed grew 606,208 bytes** vs the 2026-08-28 baseline. Diagnosed benign (WAL checkpoint growth;
  page_size 4096 × page_count 5,998,789 matches exactly, freelist 0, no gene written after 2026-08-26).
  Worth a line in `BASELINES.md` so the next arm doesn't rediscover it as a scare.

## Also standing

- Site + Cloudflare tunnel are **live** and auto-start at login via
  `site\start-site.bat` + Startup shortcut. Unaffected by a client restart.
- External evidence report: `research-inbox/2026-09-01-architecture-hunt-research.md`
  and artifact <https://claude.ai/code/artifact/32812411-7f45-4501-bfbf-e9b4d784313c>
