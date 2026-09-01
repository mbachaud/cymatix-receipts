"""mirror_branches.py -- capture receipt-like files that exist only on unmerged branches.

For each (branch, pr) pair, export every file the branch adds or changes
relative to origin/master under the receipt-bearing paths, pinned to the
branch head, into mirror-branches/<branch-slug>/ and record the head sha in
mirror-branches/BRANCHES.md. Re-run after a branch moves; a merged branch's
files show up in mirror/ on the next mirror_from_main.py run and can be
dropped from here.

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
PATHS = ["benchmarks/dogfood", "benchmarks/snow/results", "docs/benchmarks", "docs/research"]
KEEP_SUFFIX = (".json", ".jsonl", ".md", ".toml", ".csv", ".txt", ".sqlite")
BRANCHES = [
    ("bench/semantic-portfolio", 426),
    ("claude/cutoff-paraphrase-gene-issues-a77235", 427),
    ("claude/w22-eps-band-coverage", 428),
    ("perf/fts5-ingest-decay", 424),
    ("perf/hub-cutoff-default-200", 425),
    ("claude/architecture-hunt-research-e4ee87", None, "bench/semantic-portfolio"),
]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    src = Path(args.source)
    git(src, "fetch", "origin", "--quiet")
    master = git(src, "rev-parse", "origin/master").strip()
    rows = []
    for entry in BRANCHES:
        branch, pr = entry[0], entry[1]
        parent = entry[2] if len(entry) > 2 else None
        sha, ref = resolve(src, branch)
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
        changed = git(src, "diff", "--name-only", "--diff-filter=AM", base, sha, "--", *PATHS).split("\n")
        files = [f for f in changed if f and f.endswith(KEEP_SUFFIX) and "/__pycache__/" not in f]
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        if files:
            blob = subprocess.run(["git", "-C", str(src), "archive", "--format=tar", sha, "--"] + files,
                                  capture_output=True, creationflags=NOWIN)
            if blob.returncode != 0:
                raise RuntimeError("git archive failed for " + branch + ": " + blob.stderr.decode("utf-8", "replace"))
            with tarfile.open(fileobj=io.BytesIO(blob.stdout)) as tf:
                tf.extractall(out, filter="data")
        (out / "SOURCE.md").write_text(
            "# %s\n\nbranch: `%s`\nhead: `%s` (%s)\nmerge-base with origin/master: `%s`\npr: %s\nexported: %s\nfiles: %d\n\n%s\n"
            % (branch, branch, sha, ref, base, ("#%d" % pr) if pr else "local only, no PR",
               datetime.now(timezone.utc).isoformat(), len(files), "\n".join("- " + f for f in files)),
            encoding="utf-8")
        rows.append((branch, pr, sha[:12], len(files), "ok"))
        print("%-48s %s %4d files" % (branch, sha[:12], len(files)))
    DEST.mkdir(exist_ok=True)
    lines = ["# Branch mirrors", "",
             "Receipt-like files that exist only on unmerged branches of Cymatix-Context, exported at the branch head",
             "relative to origin/master `%s`. Paths scanned: %s. Regenerate with `scripts/mirror_branches.py`." % (master[:12], ", ".join("`" + p + "`" for p in PATHS)),
             "", "| branch | PR | head | files | status |", "|---|---|---|---:|---|"]
    for b, pr, sha, n, st in rows:
        lines.append("| `%s` | %s | `%s` | %d | %s |" % (b, ("#%d" % pr) if pr else "local", sha or "", n, st))
    (DEST / "BRANCHES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", DEST / "BRANCHES.md")


if __name__ == "__main__":
    main()
