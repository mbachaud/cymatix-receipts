# Tier-0 Dense Recall — Status & Handoff

**Date:** 2026-05-18
**Status:** PAUSED for handoff (user decision). Dense recall is **verified working**.
**Branch:** `claude/tier0-integration` (local only — never pushed).
**Companion:** `00-tier0-implementation-plan.md` (the design plan this executed).

---

## 1. TL;DR

Tier-0 set out to light up BGE-M3 **dense semantic retrieval** end-to-end and fix a
sharded score-scale mislabel (design path "B+b" from the plan). 

**The feature works.** Dense recall fires and materially changes `/context`
retrieval — proven by a deterministic, `$0`, no-`claude -p` probe: dense ON vs OFF
changed the delivered document set on **10/10** probed `small` queries, with a live
`dense` tier in `tier_contributions` (weight 9–28/query) and a ~+500-doc candidate
pool.

All code is committed on `claude/tier0-integration`. Nothing is pushed. The bench
A/B (~$41 spent) was **inconclusive as run** — not because dense recall failed, but
because the bench's `gold_delivered` metric is too coarse to see it (details in §4).
Four follow-ups remain; **none block "dense recall works."**

---

## 2. What was built (design: path B+b)

| PR | Commit | What |
|---|---|---|
| PR-1 | `fe1c0e8` | Compute `embedding_dense_v2` (BGE-M3) at ingest — `upsert_doc` + `context_manager.ingest`; new `dense_embed_on_ingest` knob; shared fp32 packing in `bgem3_codec.vec_to_blob`. |
| PR-3 | `f24f6d2` | Decouple dense recall from `fusion_mode` (gate → `if self._dense_embedding_enabled:`); additive-mode dense merge; sharded `_fusion_mode` relabeled `"additive"` (Decision b); flip `dense_embedding_enabled` default true. |
| test-infra | `4600528` | Autouse fake BGE-M3 codec so the non-live suite stays fast (~10 min, not ~3 h). |
| PR-2 | `9136bdd` | `build_fixture_matrix.py` dense-backfills every built `.db`; shared `backfill_dense_db()`; manifest `dense_coverage`. |
| merges | `c43214d`, `a8c50f8` | PR-2 and PR-3 merged into the integration branch. |
| review fixes | `4c806a8` | Pre-bench review: `dense_additive_min_cosine = 0.15` noise floor; SQLite-conn-leak guard in `backfill_dense_db`; stale comments. |
| CUDA autodetect | `455961c` | Dense backfill auto-selects CUDA (codec defaulted to CPU). |
| **Bug A fix** | `ddf1af0` | `/admin/swap-db` now forwards the dense/ANN/fusion knobs to `open_read_source` — see §4. |
| **Bug B fix** | `316850e` | Registry sweep stale-genome-after-swap — see §5. HEAD of the branch. |

Separate branch `claude/track-freeze-manifest` (`72fed6f`): commits the previously
untracked `scripts/freeze_matrix_manifest.py`.

Intermediate worktrees still on disk under `F:/Projects/_worktrees/helix-context/`
(`tier0-pr1-ingest-dense`, `-pr2-fixture-backfill`, `-pr3-fusion-decouple`,
`tier0-integration`, `track-freeze-manifest`). `tier0-integration` is the canonical
one; the per-PR worktrees are redundant (their branches are merged in) and can be
`git worktree remove`d.

---

## 3. Fixtures (PR-4)

6 bench fixtures rebuilt from the live `F:\Projects` tree, **100% `embedding_dense_v2`-populated**,
at `genomes/bench/matrix/` (blob) and `genomes/bench/matrix-sharded/` (sharded).
`frozen.json` written by `scripts/freeze_matrix_manifest.py`.

| Fixture | Mode | Genes |
|---|---|---|
| small | blob | 1,238 |
| medium | blob | 17,477 |
| large | blob | 28,077 |
| xl | blob | 46,479 |
| medium-sharded | sharded (6 shards) | 17,483 |
| xl-sharded | sharded (12 shards) | 46,503 |

Build notes: GPU (RTX 3080 Ti) used; the dense backfill spills to shared GPU memory
on the big shards (tune `--batch-size` lower if rebuilding). The first PR-4 build
agent crashed mid-run and was recovered manually; `small`/`medium`/`large` survived,
`xl` + sharded were rebuilt.

---

## 4. The bench journey — why the A/B was inconclusive

The plan's PR-5 was a "clean A/B": bench all 6 fixtures with dense recall OFF, then
ON, on identical fixtures. It ran but did **not** yield a clean verdict:

- **Clean A/B ran:** arm 1 (dense OFF) and arm 2 (dense ON) returned **byte-identical
  `gold_delivered_rate` on all 6 fixtures.**
- **Bug A (root cause, FIXED `ddf1af0`):** `/admin/swap-db` (`server/routes_admin.py`
  `admin_swap_db`) re-opened the genome via `open_read_source(...)` but forwarded only
  a stale subset of knobs — omitting `dense_embedding_enabled` and the dense/ANN/fusion
  cluster. Every hot-swapped fixture fell back to the `KnowledgeStore.__init__` default
  `dense_embedding_enabled=False`. So **both A/B arms actually ran dense-OFF.** The boot
  path (`context_manager.open_read_source`) passed the knobs correctly; the swap path
  had drifted. Fixed by mirroring the dense/ANN/fusion kwargs into the swap call.
- **After the fix**, a `--only small` re-check *still* showed `small` `gold_delivered`
  = 15/50, identical to dense-OFF. This was misread (in a long session) as "dense
  still inert." It is **not.** A fresh deterministic probe (§6) proved dense recall
  works; the identical number is a **coarse-metric artifact**: `gold_delivered` is a
  boolean ("does any `gold_source` path-substring appear in the delivered set"). On
  `small`, gold sets are broad prefix lists the lexical tiers already hit. Dense recall
  reshuffles *which* docs fill the budget on every query, but the boolean only flips
  when that adds/evicts a gold doc — it flipped on just 1 of 6 gold-known `small`
  queries (and that one *regressed* — see follow-up #2).

**Bench spend: ~$41** — failed arm `claude_matrix_20260517T221557Z` ($0, server-boot
crash, pre-fix); arm1 `claude_matrix_20260517T222220Z` ($18.97); arm2
`claude_matrix_20260518T001913Z` ($18.97); `small` recheck
`claude_matrix_20260518T040553Z` ($3.19). Results dirs under `benchmarks/results/`.

---

## 5. Bug B — registry sweep stale genome (FIXED `316850e`)

`server/app.py` constructs `Registry(helix.genome)`, capturing the boot store.
`admin_swap_db` reassigned `helix.genome = new_store` and closed the old store but
never updated `registry.genome` → the 60 s background `_background_registry_sweep`
(`server/helpers.py:605` → `identity/registry.py:1133`) hit `self.genome.conn.cursor()`
on the **closed** old store → repeating `sqlite3.ProgrammingError: Cannot operate on a
closed database`. `/context` itself was unaffected (it reads `helix.genome`), so the
symptom was a silent repeating background traceback.

**Fix:** `admin_swap_db` repoints `registry.genome = new_store` right after the
`helix.genome` swap and before `old_store.close()`. Regression test
`test_swap_db_repoints_registry_genome` added.

---

## 6. Verification — dense recall works (deterministic probe)

A fresh debug agent ran a server-side A/B with **no `claude -p`, no bench**: booted
the integration-worktree server, flipped `helix.toml dense_embedding_enabled` true↔false
(restart between), `/admin/swap-db` to `small.db`, and probed `/context` for 10 needle
queries with the **real BGE-M3 codec**.

- **10/10 queries delivered a different document set** with dense ON vs OFF.
- Dense ON adds a `dense` tier to `tier_contributions` (`tier_totals["dense"]` 9.1–28.4
  per query; tag-exact is ~3/doc for scale).
- Candidate pool scored: ~90–560 (OFF) → ~1180–1240 (ON) — the +500-doc dense pool.
- Confirmed independently by driving `context_manager.build_context` directly.

**Architecture note:** with `dense_embedding_enabled=true`, `context_manager._retrieve`
routes to `query_docs_ann`, which (a) calls `query_docs` as its lexical pool — that's
where the additive dense merge (`cosine × dense_additive_weight`, floor
`dense_additive_min_cosine`) runs and populates `tier_contributions["dense"]` — and
(b) makes a separate `query_docs_dense_recall` call used as its ranking key. Both are
active. The dense code itself is correct.

---

## 7. Open follow-ups (NONE block "dense recall works")

1. **Bench metric is too coarse.** `gold_delivered` (boolean) cannot see dense recall's
   reshuffle on broad-gold profiles. A meaningful re-bench needs a **rank-sensitive
   metric** (gold-doc rank / MRR) or **single-canonical-doc gold sets** per needle.
   Without this, a re-bench reproduces the §4 "identical" confusion.
2. **`dense_additive_weight = 4.0` is slightly hot.** On one probed query it pushed
   non-gold docs into the budget and *evicted* the gold docs (`gold_delivered`
   True→False) — plan risk **R1**, now observed. Recommend tuning to ~2.0–3.0, swept
   against the matrix.
3. **Issue C — ANN threshold dim mismatch.** `ann_similarity_threshold = 0.35` is
   calibrated for dim-256; the v2 vectors are dim-1024. Measured real BGE-M3 dim-1024
   cosine: unrelated passage pairs sit at **~0.50** (anisotropic space). So `0.35` is
   *below the noise floor* — inert as a cut, does **not** block Tier-0 dense recall
   (`query_docs_dense_recall` has no cosine cutoff; the additive merge uses the 0.15
   floor). But it leaves a latent `query_docs_ann` ranking quirk: lex-only docs get a
   placeholder ~0.34 while noise-level dense hits get ~0.50, so a lexically-strong
   dense-absent doc can be outranked by an irrelevant dense hit. The long-deferred
   "Stage-4" recalibration (threshold → ~0.55–0.60) fixes this. Separate work item.
4. **VaultManager** (`vault/__init__.py`) has the **same swap-staleness bug as Bug B**
   — captures the genome at construction, goes stale after `/admin/swap-db`. Low
   severity (vault is opt-in, off by default); not in the swap handler's closure so a
   slightly wider change. Flagged as a separate follow-up task.

---

## 8. To land Tier-0 (next steps for whoever picks this up)

1. **Branch disposition.** `claude/tier0-integration` holds all the work and is not
   pushed. Decide: push + open a GitHub PR for human review (the user previously chose
   a "local review pass" — a pre-bench code review was done, found no blockers, fixes
   in `4c806a8`).
2. **Optional, for a measured quality number:** implement follow-up #1 (rank-sensitive
   bench metric or tighter gold), tune `dense_additive_weight` (#2), then re-bench
   (~$19 for one dense-ON arm vs the existing dense-OFF baseline `claude_matrix_20260517T222220Z`,
   or ~$38 for a fresh clean A/B). **Do not re-bench before #1** — the current metric
   can't see dense recall.
3. File follow-ups #1–#4 as issues.

---

## 9. Housekeeping / current state

- `helix.toml` on the branch: `dense_embedding_enabled = true` (committed value;
  restored after the A/B toggling).
- No background processes / no uvicorn server running. No paid bench in flight.
- `docs/reviews/2026-05-16-deep-review/` (the plan, the 5 deep-review files, and this
  doc) is **untracked** in the main repo — commit it if you want it preserved in git.
- Non-live test suite was green (2133 passed) as of `4c806a8`; Bug B's fix added one
  test and re-verified the swap-db / dense-recall / health suites (38 passed).
- Spend: ~$41 bench compute; several hours of GPU for the PR-4 fixture rebuild.
