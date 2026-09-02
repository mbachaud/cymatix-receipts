# ScoreRift Full-Depth Audit — cymatix-context

- **Date:** 2026-08-15, run 22:51:14 → 23:37 PDT (elapsed 2788.1 s ≈ 46.5 min; pytest portion ≈ 44.4 min)
- **Target:** `F:\Projects\cymatix-context` (repo untouched — no new tracked/untracked files; verified before/after)
- **Tier:** `weekly` (deepest tier, 8 dimensions, `python` preset)
- **Scope:** FULL pytest suite — `SCORERIFT_PYTEST_MARKERS` unset (no `-m` filter), `SCORERIFT_PYTEST_TIMEOUT=5400`
- **Artifacts:** all in `F:\tmp\cymatixscontext_SR_reports` (`audit.db`, `raw_results.json`, `scores.json`, `scores.csv`, `scores.md`, driver + logs). `audit_baseline.json` was pointed here but never materialized — the sidecar only writes when a manual grade is set, and none were.

## Headline

| | |
|---|---|
| **Overall score** | **0.530** |
| **Overall grade** | **D** |
| **Health ok** | **false** |
| **Failing** | dep_freshness, security, type_coverage |
| **Divergences** | 3 (same three dimensions; auto-only — no manual baseline grades exist) |
| **Ratchet violations** | 0 |
| **tool_failure placeholders** | **None** — every dimension returned real tool evidence |

**Evidence trust:** all 8 auto-confidences are >= 0.6 (min: security at 0.60; trust floor is 0.50), and no detail dict carries `"tool_failure": true`. The health verdict and the failing list are built entirely on trusted evidence. The `divergent: true` flags on the three 0.0-score dimensions are not auto-vs-manual disagreements (there is no manual baseline); they mirror the failing status.

## Dimension scores vs the two prior CI-scope passes (same day, `-m "not slow and not live and not perf"`)

| Dimension | Full run (this) | Baseline (CI scope) | Post-merge rerun (CI scope) | Moved? |
|---|---|---|---|---|
| test_coverage | **0.9995** (3811 passed / 2 failed / 3813 pass+fail) | 1.0 (3812/3812) | 0.9997 (3803 passed / 1 failed, 3804 collected) | **Yes — see below** |
| lint_score | 0.78 (11 ruff errors) | 0.78 (11) | 0.78 (11) | No |
| type_coverage | 0.0 (106 mypy errors) | 0.0 (106) | 0.0 (106) | No |
| dep_freshness | 0.0 (41 of 142 outdated) | 0.0 (41/142) | 0.0 (41/142) | No |
| doc_coverage | 0.523 (10,562/33,210 = 31.8%, README yes) | 0.523 (31.8% of 33,210) | 0.523 | No |
| security | 0.0 (semgrep: 0 errors, 27 warnings) | 0.0 (0/27) | 0.0 (0/27) | No |
| complexity | 1.0 (AST: 37,669 fns, avg 3.91, max 155) | 1.0 (avg 3.91, max 155) | 1.0 | No |
| import_hygiene | 0.94 (2 violations) | 0.94 (2) | 0.94 (2) | No |
| **Overall** | **0.530 (D)** | 0.530 (D) | ~0.530 (D) | No |

Seven of eight dimensions are bit-identical to this morning's CI-scope passes — expected, since only test_coverage's inputs change when the marker filter is dropped. The overall D/0.530 is unchanged.

## What the FULL suite adds vs the CI scope

- **Collected:** 3,939 node IDs (fresh `.pytest_cache/v/cache/nodeids`) vs 3,812 (baseline CI scope) / 3,804 (post-merge CI scope) — the `slow`/`live`/`perf` markers gate ~127–135 additional tests.
- **Executed to a pass/fail verdict:** 3,813 (3,811 passed + 2 failed). The remaining ~126 collected-but-unverdicted tests were skipped/xfailed at runtime (e.g., live tests without their external services); scorerift's parser counts only `passed`/`failed`.
- **Pass rate:** 99.95% (2 failures) vs 100% baseline / 99.97% (1 failure) post-merge. The full suite surfaces **one additional failure** over the post-merge CI-scope run.

## Failing tests (from `.pytest_cache/v/cache/lastfailed`, written by this run at 23:35:40 — no rerun performed)

The fresh `lastfailed` contains three node IDs:

1. `tests/test_mcp_server.py::test_helix_announce_tool_calls_bridge_announce`
2. `tests/test_no_helix_leftovers.py::test_cymatix_console_scripts_present`
3. `tests/test_install_observability.py::test_bash_install_script_parses`

Attribution caveat — the run counted exactly **2** failures, but `lastfailed` persists entries for previously-failed tests that did not execute (e.g., runtime-skipped) in the latest session:

- `test_bash_install_script_parses` is **new** versus the pre-run `lastfailed` (20:37 snapshot) and entries are only ever added on an actual failure → it **definitely failed in this run**.
- The other two are carried over from the earlier CI-scope rerun's `lastfailed`. Exactly **one of them failed again in this run** and the other did not execute (had both run-and-failed the count would be 3; had one run-and-passed it would have been removed, leaving 2 entries). The earlier post-merge rerun counted 1 FAILED against the same two cached entries, so one of the pair was already a carried non-executing entry this morning. Which of the two is the live failure cannot be determined from the cache alone without rerunning.

## Run integrity notes

- **First attempt lost:** the initial launch (21:49) was killed at the 60-minute harness background-task cap while pytest was still mid-suite; pytest writes its cache only at session end, so no partial data existed. The audit was relaunched fully detached (WMI-parented, `run_full_audit.bat` → `run_full_audit.py`) at 22:51 and completed clean (exit 0). Net effect: one completed suite execution, plus ~58 min of wall-clock burned by the killed first attempt.
- An unrelated ERB ablation benchmark (`ablation_ladder.py`, running since 16:59) shared the box during both attempts.
- Expected harmless `SyntaxWarning` noise from AST-parsing cymatix files appeared on stderr (`run_stderr.log`), as predicted.
- `pip list --outdated` (dep_freshness) matched this morning's counts exactly, so network variance did not distort the comparison.

*Generated from `raw_results.json` (engine output) + scorerift exporters; scores also persisted in `audit.db`.*
