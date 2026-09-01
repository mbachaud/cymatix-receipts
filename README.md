# cymatix-receipts

Private evidence archive for [Cymatix Context](https://github.com/mbachaud/Cymatix-Context).

This repository is the durable home for the measurement trail behind the
project: benchmark receipts, campaign write-ups, research captures, and the
archived knowledge-store snapshots that those measurements ran against. The
code repository stays lean; the evidence lives here.

Nothing in this repository is a claim on its own. A receipt is a record of what
one run produced under one configuration. Reading it as a result requires the
citation rules below.

## Layout

```
mirror/                     tracked receipt corpus exported from the code repo
  benchmarks/dogfood/       arm, baseline and ladder receipts, ERB receipts, w32 receipts
  benchmarks/snow/results/  snow harness results
  benchmarks/results/faithfulness/
  docs/benchmarks/          campaign write-ups, BASELINES.md, docs/benchmarks/data/
  docs/research/data/       research datasets
  MIRROR.md                 source repo, commit sha, export date, file and byte counts
research-inbox/             research captures with no home in the code repo
untracked/
  benchmarks/results/       result JSONs snapshotted from the main working tree
  erb-phase2-tooling/       pool-depth probe and verification harnesses, smoke receipts
beds/                       manifest for knowledge-store snapshots published as release assets
scripts/                    regeneration and verification scripts
index.json                  one entry per archived file, with sha256
```

`mirror/` is an export from a pinned commit, never from a working tree, so every
file in it can be traced back to a single sha. `research-inbox/` and `untracked/`
are plain file copies of material that is gitignored upstream and would otherwise
be lost.

## Citation convention

**A receipt is citable only if it has a row in the main repository's baselines
ledger.** The ledger is the authority on what a given number means and what it
may be compared against:

<https://github.com/mbachaud/Cymatix-Context/blob/master/docs/benchmarks/BASELINES.md>

A mirrored copy sits at `mirror/docs/benchmarks/BASELINES.md`, pinned to the
export commit. The upstream file is the live version and wins on any conflict.

The ledger's rules, in brief:

1. **Row scoping.** Compare arms only within their own row. "A receipt without a
   row here is not comparable to anything."
2. **Frozen tags.** Measurement runs against a frozen tag, never a moving branch.
3. **Ingest concurrency.** Every bed records the concurrency it was built at
   (`ingest_c`). Cross-bed comparisons require matching `ingest_c`, because
   parallel LLM tagging changes gene content and tags even at temperature zero.
   `unknown` is a legal value and means not comparable across beds.
4. **Tagger version.** Tags are part of the bed content digest, so a tagger
   change is a bed change. Cross-bed comparisons require matching
   `tagger_version`. Everything built before 2026-08-30 is version 1.

Two further cautions that apply throughout this archive. Some receipts were
invalidated for comparability by later bed maintenance; the ledger marks those
rows and says why. And several campaigns publish a final-order basis (`fr@12`)
in the prose while the receipts carry a delivered basis
(`delivered_gold_rate`); check which basis a number is on before quoting it.

## Archived beds

Knowledge-store snapshots are published as **GitHub Release assets** on this
repository, as zstd-compressed SQLite files named `<bed>.db.zst`. Per-asset
sha256 digests live in `beds/MANIFEST.json`, which arrives with the first
release. See `beds/README.md`. No git LFS is used anywhere in this repository.

## Privacy

**This repository stays private until an audit clears it.**

Cymatix Context ran as a transparent proxy in its April 2026 era, and the
pipeline persists query and response exchanges back into the knowledge store by
design (pipeline stage 6). Knowledge stores from that period, and receipts or
research captures derived from them, may therefore contain real conversational
content, file paths, and other incidental personal data that was never intended
for publication. The EnronQA-derived material carries the additional constraints
of its own source corpus.

Nothing here should be made public, quoted externally, or attached to an issue
in a public repository until the relevant artifacts have been reviewed for
persisted exchanges and scrubbed or excluded.

## Regenerating

Three stdlib-only scripts, run with native `python` (3.14 on the authoring box):

```bash
# re-export mirror/ and MIRROR.md from a pinned commit of the code repo
python scripts/mirror_from_main.py --source <path-to-cymatix-context-checkout> --ref origin/master

# rebuild index.json over mirror/, research-inbox/ and untracked/
python scripts/build_index.py

# recompute every sha256 and report drift (exit 1 on any mismatch)
python scripts/verify_index.py
```

`mirror_from_main.py` streams `git archive` from the requested ref, so it never
reads the source working tree and cannot pick up uncommitted state. It replaces
`mirror/` wholesale on each run.

`research-inbox/` and `untracked/` are captured by hand rather than by script,
because their sources are gitignored working-tree paths that move between
worktrees. `build_index.py` picks up whatever is present in them.

A `.gitattributes` at the repository root disables all text conversion (`* -text`).
This matters: without it, git would rewrite line endings on checkout and every
sha256 in `index.json` would fail to verify on a fresh clone.
