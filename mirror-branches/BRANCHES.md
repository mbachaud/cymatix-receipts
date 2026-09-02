# Branch mirrors

Receipt-like files that exist only on unmerged branches of Cymatix-Context, exported at the branch head
relative to origin/master `2644c3e44038`. Paths scanned: `benchmarks/dogfood`, `benchmarks/snow/results`, `docs/benchmarks`, `docs/research`, `docs/audits`, `benchmarks/scbench`. Regenerate with `scripts/mirror_branches.py`.
Refs resolve as `refs/remotes/origin/<branch>` first, then `refs/heads/<branch>` in the `--source` checkout,
so local-only branches are mirrored too; each `SOURCE.md` records the ref used and any reading note.
Some mirrored trees (`codex__scbench-cymatix-ab`) carry paths over 200 characters; on Windows, clone with
`git config core.longpaths true` (or clone to a short root) or checkout fails with "Filename too long".

| branch | PR | head | files | status |
|---|---|---|---:|---|
| `bench/semantic-portfolio` | #426 | `b5eb803d3f63` | 54 | ok |
| `claude/cutoff-paraphrase-gene-issues-a77235` | #427 | `b266fb814b45` | 9 | ok |
| `claude/w22-eps-band-coverage` | #428 | `a56ae8b79541` | 4 | ok |
| `perf/fts5-ingest-decay` | #424 | `a565dd615c54` | 5 | ok |
| `perf/hub-cutoff-default-200` | #425 | `097a79b62e75` | 2 | ok |
| `claude/architecture-hunt-research-e4ee87` | local | `45a4055726c8` | 31 | ok |
| `claude/scorerift-audit-cymatix-0d6262` | local | `082217569191` | 13 | ok |
| `claude/ab-data-cymatics-pki-dff9c6` | local | `daaa6af50b4c` | 14 | ok |
| `claude/codebase-audit-weaknesses-96a7da` | local | `70e2a2fa9d83` | 2 | ok |
| `codex/scbench-cymatix-ab` | local | `9312cde85e88` | 985 | ok |
