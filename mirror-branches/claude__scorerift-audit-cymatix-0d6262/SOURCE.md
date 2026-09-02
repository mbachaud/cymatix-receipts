# claude/scorerift-audit-cymatix-0d6262

branch: `claude/scorerift-audit-cymatix-0d6262`
head: `082217569191f44267bd22e02eb11b3c1c7f0620` (refs/heads/claude/scorerift-audit-cymatix-0d6262)
diff base: `e0099873b49f1f123d1a1144debd49665d0dac0c` (merge-base with origin/master)
pr: local only, no PR
exported: 2026-09-02T05:56:04.640226+00:00
files: 13
bytes: 56086 (largest 32768: `docs/audits/2026-08-15-scorerift-weekly/audit.db`)

## Reading note: KILL receipt

This branch archives the 2026-08-15 full-depth ScoreRift weekly run byte-exact, plus a
validity addendum (`docs/audits/2026-08-15-scorerift-weekly/README.md`) written after a
2026-08-16 integrity review. The addendum is a **kill receipt**: the D/0.530 headline is
NOT a grade of master. The run graded the `codex/snowv2build` checkout (v0.8.6 + docs,
69 commits behind master), its doc_coverage/complexity corpus was 69.4% `.claude/worktrees`
duplicates (ScoreRift rglob does not exclude dot-directories), and both counted test
failures were environmental. Only `dep_freshness` is trustworthy. Do not cite the grade;
cite the addendum. `.scorerift.json` is the 4-line preset pin from the repo root. The
commit is local-only (never pushed) and was mirrored via the refs/heads fallback.

- .scorerift.json
- docs/audits/2026-08-15-scorerift-weekly/README.md
- docs/audits/2026-08-15-scorerift-weekly/SUMMARY.md
- docs/audits/2026-08-15-scorerift-weekly/audit.db
- docs/audits/2026-08-15-scorerift-weekly/raw_results.json
- docs/audits/2026-08-15-scorerift-weekly/run_exitcode.txt
- docs/audits/2026-08-15-scorerift-weekly/run_full_audit.bat
- docs/audits/2026-08-15-scorerift-weekly/run_full_audit.py
- docs/audits/2026-08-15-scorerift-weekly/run_stderr.log
- docs/audits/2026-08-15-scorerift-weekly/run_stdout.log
- docs/audits/2026-08-15-scorerift-weekly/scores.csv
- docs/audits/2026-08-15-scorerift-weekly/scores.json
- docs/audits/2026-08-15-scorerift-weekly/scores.md
