# ScoreRift Weekly Audit — 2026-08-15 — VALIDITY ADDENDUM

> **⚠ Do not cite the D/0.530 headline as a grade of master.** This directory archives the
> artifacts of the 2026-08-15 full-depth ScoreRift run (22:51 → 23:37 PDT, exit 0) exactly as
> produced, but a post-run integrity review (2026-08-16) found two defects that invalidate the
> headline. The artifacts are preserved byte-exact for provenance; this README is the
> authoritative reading guide.

## Defect 1 — wrong branch graded

All three 2026-08-15 passes (baseline CI-scope, post-merge CI-scope, full weekly) graded the
checkout at `F:\Projects\cymatix-context`, which was on **`codex/snowv2build`** — **69 commits
behind master** (merge-base `156548c` = the v0.8.6 release, 2026-08-05, plus 2 docs-only branch
commits). The audited tree is effectively *v0.8.6 + docs*, missing among others the RRF
de-flake fix (`d077b7c`), the swap-db kwargs fix (`299e9e2`), the PKI read gate (`420576b`),
and the #313 spacy pins. Proof the input never moved: 7 of 8 dimensions were bit-identical
across all three passes — the "post-merge" pass measured nothing post-merge.

## Defect 2 — corpus pollution in doc_coverage / complexity

ScoreRift's `doc_coverage` and `complexity` scans (`python_project.py` rglob filters) do not
exclude dot-directories, so they ingested the three git worktrees under `.claude/worktrees/`:
**1,624 of 2,341 scanned files (69.4%) were other-branch repo duplicates.** Replicating the
exact algorithm on clean master tracked files gives:

| Dimension | Audit recorded | Clean master |
|---|---|---|
| doc_coverage | 0.523 (31.8% of 33,210) | **0.593** (41.8% of a 622-file corpus) |
| complexity detail | 37,669 fns, avg 3.91 | 6,358 fns, avg 2.60 (score 1.0 either way) |

## The two counted test failures — both environmental

- `test_cymatix_console_scripts_present` — the environment has **no installed
  cymatix-context distribution at all** (helix uninstall done, `pip install -e .` never
  re-run; the `.venv/Scripts/*.exe` shims exist but `entry_points()` metadata does not).
  Not a code regression; the failing file is byte-identical to master.
- `test_bash_install_script_parses` — fails only via `subprocess.TimeoutExpired` (10s) or
  `bash -n` non-zero (the execvpe/no-distro case is converted to skip). Passes standalone;
  the ERB ablation bench loaded the box throughout the audit. Leading explanation:
  load-induced timeout on the WSL-shim probe.
- The third `lastfailed` entry, `test_helix_announce_tool_calls_bridge_announce`, is a
  **cache fossil**: the test was removed by `34e241e` (2026-07-22 MCP rename) and exists on
  no branch; pytest's lastfailed never prunes uncollected nodes.

## What survives

- **dep_freshness (0.0, 41/142 outdated)** is the only dimension that is trustworthy
  evidence — it graded the project venv, which is checkout-independent. (Caveat: it scopes
  a shared global-env view; most of the outdated set is not a declared project dependency.)
- complexity's 1.0 is robust (both polluted and clean averages are ≤ 5).
- lint/type/security counts were stable across the stale tree and master where re-checked
  (semgrep's 27 warnings reproduce exactly on master), but note the **toolchain split**:
  `.venv/Scripts` lacks ruff/mypy/semgrep, so those three dimensions ran from the core
  Python 3.14 env while pytest/pip ran in the project venv. mypy's 106 lines are an
  **aborted run** (exit 2, module-name collision in `scripts/bench_chain/erb500k_scored.py`)
  — 100% import-graph noise, 0% annotation measurement.

## Re-run protocol (for the next valid grade)

1. Wait for the ERB ablation bench to finish (box load contaminates the pytest dimension).
2. `pip install -e .` in the project venv (restores console-script entry points); ideally
   install ruff/mypy/semgrep into the same venv so all 8 dimensions grade one environment.
3. Delete the fossil `.pytest_cache/v/cache/lastfailed` in the graded checkout.
4. Grade a true master tree — the clean master worktree qualifies and sidesteps the
   dot-dir pollution bug entirely; if grading the main checkout, switch it back to master
   and patch ScoreRift's rglob filters to exclude dot-dirs first.
5. Same env contract for comparability: `SCORERIFT_PYTEST_MARKERS` unset,
   `SCORERIFT_PYTEST_TIMEOUT=5400`, artifacts to a dated dir archived here afterwards.
6. Set manual baseline grades so the divergence sidecar (`audit_baseline.json`)
   materializes and divergence semantics become meaningful.

Expected deltas on a clean run: doc_coverage ≈ 0.593, test_coverage 1.0 absent load,
dep_freshness stays 0.0 until the venv is actually upgraded; type_coverage and security
remain the open questions the re-run must answer against master code.
