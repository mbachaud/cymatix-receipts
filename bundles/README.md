# Git bundles of deleted branches

Each bundle holds the commits of a Cymatix-Context branch that was deleted on GitHub on 2026-09-02 after its viable content was ported (PRs #435-#438) or archived. Restore with `git bundle unbundle <file>` or `git fetch <file> <branch>`; bundles are relative to origin/beta at 21606a0, so fetch them into a clone that has that commit.

| bundle | bytes | sha256 (16) |
|---|---:|---|
| `claude_ab-data-cymatics-pki-dff9c6.bundle` | 411803 | 21724f3d1233ea34 |
| `claude_codebase-audit-weaknesses-96a7da.bundle` | 45418 | eba7da68dfa8aa26 |
| `codex_scbench-cymatix-ab.bundle` | 4748296 | 34a560317e5ea7b0 |
| `feat_finish-cymatix-rename.bundle` | 286349 | 6fde72033952c678 |
