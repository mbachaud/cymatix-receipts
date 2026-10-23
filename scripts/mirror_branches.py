"""mirror_branches.py -- capture receipt-like files that exist only on unmerged branches.

For each (branch, pr) pair, export every file the branch adds or changes
relative to origin/master under the receipt-bearing paths, pinned to the
branch head, into mirror-branches/<branch-slug>/ and record the head sha in
mirror-branches/BRANCHES.md. Re-run after a branch moves; a merged branch's
files show up in mirror/ on the next mirror_from_main.py run and can be
dropped from here.

Branch refs resolve as refs/remotes/origin/<branch> first and fall back to
refs/heads/<branch>, so a local-only branch in the --source checkout (never
pushed) is mirrored the same way as a remote one; SOURCE.md records which
ref was used.

    python scripts/mirror_branches.py --source <cymatix-context worktree>
"""
import argparse
import io
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "mirror-branches"
PATHS = ["benchmarks/dogfood", "benchmarks/snow/results", "docs/benchmarks", "docs/research",
         "docs/audits", "benchmarks/scbench"]
KEEP_SUFFIX = (".json", ".jsonl", ".md", ".toml", ".csv", ".txt", ".sqlite")
# Some receipt trees carry provenance in shapes the default suffix list drops
# (binary audit dbs, driver scripts, run logs, harness yaml). Widen per prefix
# rather than globally so the dogfood/docs mirrors keep their existing shape.
EXTRA_KEEP = {
    "docs/audits/": (".db", ".log", ".py", ".bat"),
    "benchmarks/scbench/": (".db", ".log", ".yaml", ".yml", ".py"),
    # Run logs committed next to receipts (e.g. shortlist_prefix_stability_*.log).
    "benchmarks/dogfood/erb/receipts/": (".log",),
    # Jev (System One) harnesses live next to their receipts on a local-only branch.
    "benchmarks/dogfood/jev/": (".py",),
}
# Per-branch extra pathspecs outside PATHS (e.g. a repo-root pin file that
# belongs with the archived run).
EXTRA_PATHS = {
    "claude/scorerift-audit-cymatix-0d6262": [".scorerift.json"],
}
# Per-branch reading notes appended to SOURCE.md.
NOTES = {
    "claude/scorerift-audit-cymatix-0d6262": (
        "## Reading note: KILL receipt\n\n"
        "This branch archives the 2026-08-15 full-depth ScoreRift weekly run byte-exact, plus a\n"
        "validity addendum (`docs/audits/2026-08-15-scorerift-weekly/README.md`) written after a\n"
        "2026-08-16 integrity review. The addendum is a **kill receipt**: the D/0.530 headline is\n"
        "NOT a grade of master. The run graded the `codex/snowv2build` checkout (v0.8.6 + docs,\n"
        "69 commits behind master), its doc_coverage/complexity corpus was 69.4% `.claude/worktrees`\n"
        "duplicates (ScoreRift rglob does not exclude dot-directories), and both counted test\n"
        "failures were environmental. Only `dep_freshness` is trustworthy. Do not cite the grade;\n"
        "cite the addendum. `.scorerift.json` is the 4-line preset pin from the repo root. The\n"
        "commit is local-only (never pushed) and was mirrored via the refs/heads fallback."
    ),
    "codex/scbench-cymatix-ab": (
        "## Reading note\n\n"
        "SCBench (slopcodebench) Codex/Cymatix paired regression-resistance A/B harness campaign\n"
        "receipts committed on the branch: qualification pairs and invalid-attempts (with sidecar\n"
        "`cymatix.genome.db` files as committed, no -wal/-shm), the Luna pilot and Terra campaign\n"
        "manifests/READMEs/analyses, and the two branch-only Terra docs. Frozen tags on origin:\n"
        "`bench/scbench-luna-2026-08-08` (0b125ea) and `bench/scbench-terra-2026-08-11` (9312cde).\n"
        "The ~476 MB of gitignored pair receipts (`campaigns/*/pairs/`, `preflight.json`, Terra\n"
        "`analysis-v2.*`) are NOT in git anywhere; they are archived as release assets of this\n"
        "repository, see `captures/scbench/MANIFEST.json`. Verdicts: Luna pilot NOT graduated\n"
        "(issue #359, STOP); Terra v2 `no_detectable_difference`, all safety gates pass."
    ),
    "claude/ab-data-cymatics-pki-dff9c6": (
        "## Reading note\n\n"
        "2026-08-09 A/B data campaign (waves 0a-3d): paired PKI/tag-tier ladder passes at 100k and\n"
        "829k (`wave3b_*`, `wave3d_*`), wave0a smoke/timing receipts, erb10k delivered-gold A/B, and\n"
        "the 701-line candidate-cascade map. Beta's ledger Addendum 7 (ported 2026-08-19) cites the\n"
        "wave3b/wave3d receipts as living only on this branch. Never a PR."
    ),
    "claude/codebase-audit-weaknesses-96a7da": (
        "## Reading note\n\n"
        "2026-08-08 audit-remediation branch; the docs/benchmarks files here are the branch's\n"
        "versions of the 2026-07-29 clean-bed rerun and cymatics-ablation verdict notes (retraction\n"
        "annotations later superseded on beta by #354/#388). Code from this branch landed partially\n"
        "via PR #391; the rest is a port decision, not a receipt."
    ),
    "claude/wider-funnel-architecture-f7d3b6": (
        "## Reading note: pinned below the tip\n\n"
        "Local-only branch (never pushed). Its 2026-09-03 commit abe4f246 adds the 2026-09-02\n"
        "research receipts and write-ups: wider-funnel tail-lane probes, agent findability on the\n"
        "crater, the beta 947k full check, the needle-bank identity hazard, code-path identifier\n"
        "receipts. The branch tip df6284b5 then untracks every receipt tree, so exporting the tip\n"
        "would capture nothing; this mirror is pinned to abe4f246 instead (PINS in\n"
        "scripts/mirror_branches.py). Until 2026-10-04 these files sat in mirror/ via the 78b33df\n"
        "export, which was taken from abe4f246 rather than master; they moved here when mirror/ was\n"
        "re-exported from origin/master."
    ),
    "claude/jev-packet-assembly-test-138065": (
        "## Reading note: EXPERIMENTAL external model\n\n"
        "Local-only branch (never pushed), cut from `bench/c580-multicorpus` for its c4000 classcap\n"
        "profile; the diff base is that branch, so only the Jev files are here. Jev (TypeSafe\n"
        "\"System One\", jev-1.14.0) is a proprietary hosted API, not part of the cymatix pipeline.\n"
        "Receipts: 239b synthetic bed (know/miss 72/72), ERB 947k c4000 classcap with cymatix\n"
        "incoming rankings (packet AUROC 0.906; delivery identical to the 10-19 ladder 470/470),\n"
        "and the paired no-incoming ablation (0.900, delta CI [-0.015, +0.004]). Each receipt\n"
        "carries every raw Jev response, so `--rescore` needs no key. Write-up:\n"
        "`docs/benchmarks/2026-10-23-jev-system-one-packet-judge.md` on the System One PR (#522).\n\n"
        "Local comparison (`laya_*.json`): Laya 0.4.14 (ConvAI Innovations, Apache-2.0) served by\n"
        "laya-serve on an RTX 3080 Ti, checkpoints english@512 / multilingual@8192 /\n"
        "typed-decisions@1024 (revision 7b928d82), same no-incoming questions and the same 470 ERB\n"
        "packets as the Jev arm. ERB packet AUROC 0.563 (multilingual) / 0.480 (typed-decisions) vs\n"
        "Jev 0.900; `laya_truncation_2026-10-23.txt` gives Laya's own truncation counts (typed-decisions\n"
        "read p50 944 of 9,057 packet tokens)."
    ),
}
# Export a branch at a fixed commit instead of its head, when the head is not
# the commit that carries the receipts (e.g. a tip that untracks them).
PINS = {
    "claude/wider-funnel-architecture-f7d3b6": "abe4f246",
}
BRANCHES = [
    ("bench/semantic-portfolio", 426),
    ("claude/cutoff-paraphrase-gene-issues-a77235", 427),
    ("claude/w22-eps-band-coverage", 428),
    ("perf/fts5-ingest-decay", 424),
    ("perf/hub-cutoff-default-200", 425),
    ("claude/architecture-hunt-research-e4ee87", None, "bench/semantic-portfolio"),
    ("claude/scorerift-audit-cymatix-0d6262", None),
    ("claude/ab-data-cymatics-pki-dff9c6", None),
    ("claude/codebase-audit-weaknesses-96a7da", None),
    ("codex/scbench-cymatix-ab", None),
    ("claude/wider-funnel-architecture-f7d3b6", None),
    ("claude/jev-packet-assembly-test-138065", None, "bench/c580-multicorpus"),
]
# Keep every pathspec batch comfortably under the Windows command-line limit.
ARCHIVE_ARG_BYTES = 24000


def git(src, *args, text=True):
    r = subprocess.run(["git", "-C", str(src)] + list(args), capture_output=True, text=text,
                       creationflags=NOWIN, encoding="utf-8" if text else None, errors="replace" if text else None)
    if r.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + ": " + (r.stderr if text else r.stderr.decode("utf-8", "replace")))
    return r.stdout


def resolve(src, branch):
    for ref in ("refs/remotes/origin/" + branch, "refs/heads/" + branch):
        try:
            return git(src, "rev-parse", "--verify", "--quiet", ref).strip(), ref
        except RuntimeError:
            continue
    return None, None


def keep(path):
    if "/__pycache__/" in path or path.rsplit("/", 1)[-1] == ".gitignore":
        return False
    if path.endswith(KEEP_SUFFIX):
        return True
    for prefix, extra in EXTRA_KEEP.items():
        if path.startswith(prefix) and path.endswith(extra):
            return True
    return False


def batches(files):
    batch, size = [], 0
    for f in files:
        if batch and size + len(f) + 3 > ARCHIVE_ARG_BYTES:
            yield batch
            batch, size = [], 0
        batch.append(f)
        size += len(f) + 3
    if batch:
        yield batch


def export(src, sha, files, out):
    for batch in batches(files):
        blob = subprocess.run(["git", "-C", str(src), "archive", "--format=tar", sha, "--"] + batch,
                              capture_output=True, creationflags=NOWIN)
        if blob.returncode != 0:
            raise RuntimeError("git archive failed for " + sha + ": " + blob.stderr.decode("utf-8", "replace"))
        with tarfile.open(fileobj=io.BytesIO(blob.stdout)) as tf:
            tf.extractall(out, filter="data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--only", help="re-export just this branch and update only its row in "
                                   "BRANCHES.md (other mirrors, possibly of deleted branches, untouched)")
    args = ap.parse_args()
    src = Path(args.source)
    git(src, "fetch", "origin", "--quiet")
    master = git(src, "rev-parse", "origin/master").strip()
    rows = []
    entries = [e for e in BRANCHES if not args.only or e[0] == args.only]
    if args.only and not entries:
        raise SystemExit("--only %s: not in BRANCHES" % args.only)
    for entry in entries:
        branch, pr = entry[0], entry[1]
        parent = entry[2] if len(entry) > 2 else None
        sha, ref = resolve(src, branch)
        if sha and branch in PINS:
            pinned = git(src, "rev-parse", "--verify", PINS[branch] + "^{commit}").strip()
            git(src, "merge-base", "--is-ancestor", pinned, sha)  # raises unless on the branch
            ref = "pinned %s (branch head %s via %s)" % (pinned[:12], sha[:12], ref)
            sha = pinned
        slug = branch.replace("/", "__")
        out = DEST / slug
        if not sha:
            rows.append((branch, pr, None, 0, "branch not found"))
            print("skip", branch, "(not found)")
            continue
        base = git(src, "merge-base", master, sha).strip()
        if parent:
            psha, _ = resolve(src, parent)
            if psha:
                base = git(src, "merge-base", psha, sha).strip()
        paths = PATHS + EXTRA_PATHS.get(branch, [])
        changed = git(src, "diff", "--name-only", "--diff-filter=AM", base, sha, "--", *paths).split("\n")
        files = [f for f in changed if f and keep(f)]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        if files:
            export(src, sha, files, out)
        sizes = {f: (out / f).stat().st_size for f in files}
        biggest = max(sizes.items(), key=lambda kv: kv[1]) if sizes else ("", 0)
        note = NOTES.get(branch, "")
        (out / "SOURCE.md").write_text(
            "# %s\n\nbranch: `%s`\nhead: `%s` (%s)\ndiff base: `%s`%s\npr: %s\nexported: %s\nfiles: %d\nbytes: %d (largest %d: `%s`)\n\n%s%s\n"
            % (branch, branch, sha, ref, base,
               (" (merge-base with parent branch `%s`)" % parent) if parent else " (merge-base with origin/master)",
               ("#%d" % pr) if pr else "local only, no PR",
               datetime.now(timezone.utc).isoformat(), len(files), sum(sizes.values()), biggest[1], biggest[0],
               (note + "\n\n") if note else "", "\n".join("- " + f for f in files)),
            encoding="utf-8")
        rows.append((branch, pr, sha[:12], len(files), "ok" if biggest[1] < 95 * 1000 * 1000 else "ok (file over 95 MB: %s)" % biggest[0]))
        print("%-48s %s %4d files %10d bytes (%s)" % (branch, sha[:12], len(files), sum(sizes.values()), ref))
    DEST.mkdir(exist_ok=True)
    if args.only:
        index = DEST / "BRANCHES.md"
        b, pr, sha, n, st = rows[0]
        row = "| `%s` | %s | `%s` | %d | %s |" % (b, ("#%d" % pr) if pr else "local", sha or "", n, st)
        old = index.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in old if not ln.startswith("| `%s` |" % b)]
        index.write_text("\n".join(kept + [row]) + "\n", encoding="utf-8")
        print("updated row in", index)
        return
    lines = ["# Branch mirrors", "",
             "Receipt-like files that exist only on unmerged branches of Cymatix-Context, exported at the branch head",
             "relative to origin/master `%s`. Paths scanned: %s. Regenerate with `scripts/mirror_branches.py`." % (master[:12], ", ".join("`" + p + "`" for p in PATHS)),
             "Refs resolve as `refs/remotes/origin/<branch>` first, then `refs/heads/<branch>` in the `--source` checkout,",
             "so local-only branches are mirrored too; each `SOURCE.md` records the ref used and any reading note.",
             "Some mirrored trees (`codex__scbench-cymatix-ab`) carry paths over 200 characters; on Windows, clone with",
             "`git config core.longpaths true` (or clone to a short root) or checkout fails with \"Filename too long\".",
             "", "| branch | PR | head | files | status |", "|---|---|---|---:|---|"]
    for b, pr, sha, n, st in rows:
        lines.append("| `%s` | %s | `%s` | %d | %s |" % (b, ("#%d" % pr) if pr else "local", sha or "", n, st))
    (DEST / "BRANCHES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", DEST / "BRANCHES.md")


if __name__ == "__main__":
    main()
