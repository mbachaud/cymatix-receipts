"""CE-signal know replays over the 30 #482 beds, one at a time (2026-10-08).

Same beds, needle/gold files and env as tuning_campaign_2026-10-05 (shipped
cymatix.toml, postflip_default arm, k=12), plus --ce-model. ERB runs last on
the v0.11.1 witness snapshot so the shared bed is never touched. Resumable: a
bed whose receipt exists is skipped. No latency claims (runs may overlap other
work), so no cold-bed gate.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

WT = Path(r"F:\Projects\cymatix-context\.worktrees\ce-replays-20261008")
RUN = Path(r"F:\tmp\ce-replays-20261008")
CE = "cross-encoder/ms-marco-MiniLM-L-6-v2"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
D = WT / "benchmarks" / "dogfood"

FORUMS = ["android", "english", "gaming", "gis", "mathematica", "physics", "programmers",
          "stats", "tex", "unix", "webmasters", "wordpress"]
BEIR = (["beir_scifact", "beir_nfcorpus", "beir_arguana", "beir_scidocs", "beir_fiqa", "beir_trec_covid",
         "beir_webis_touche2020"] + [f"beir_cqadupstack_{f}" for f in FORUMS] + ["beir_quora"])
BEDS = {t: (rf"F:\tmp\{t}_bed\{t}.db", t, f"needles_resolved_{t}_full.json", f"gold_by_needle_{t}.json")
        for t in BEIR}
for t in ("coderag_solutions", "coderag_docs", "cosqa", "swebench"):
    BEDS[t] = (rf"F:\tmp\{t}_bed\{t}.db", t, f"needles_resolved_{t}_full.json", f"gold_by_needle_{t}.json")
BEDS.update({
    "enronqa_v2": (r"F:\tmp\enronqa_bed_v2\enronqa.db", "enronqa", "needles_resolved_enronqa_full.json",
                   "gold_by_needle_enronqa.json"),
    "locomo": (r"F:\tmp\locomo_bed\locomo.db", "locomo", "needles_resolved_locomo_full.json",
               "gold_by_needle_locomo.json"),
    "financebench": (r"F:\tmp\financebench_bed\financebench.db", "financebench",
                     "needles_resolved_financebench_full.json", "gold_by_needle_financebench.json"),
    "muloc": (r"F:\tmp\muloc_bed\muloc.db", "muloc", "needles_resolved_muloc_full.json", "gold_by_needle_muloc.json"),
    "enronqa_padded": (r"F:\tmp\enronqa_padded_bed\enronqa_padded.db", "enronqa_padded",
                       "needles_resolved_enronqa_full.json", "gold_by_needle_enronqa.json"),
    "erb_947k": (r"F:\tmp\witness-v0111-candidate\erb_blob_v09x.db", "erb", "needles_resolved_v09x_full.json",
                 "gold_by_needle_v09x.json"),
})


def out_path(name):
    return RUN / "receipts" / f"know_replay_ce_{name}_2026-10-08.json"


def main():
    (RUN / "receipts").mkdir(parents=True, exist_ok=True)
    lock = RUN / "runner.lock"
    if lock.exists():
        raise SystemExit(f"claimed by pid {lock.read_text().strip()}")
    lock.write_text(str(os.getpid()))
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    env = dict(os.environ)
    for k in ("CYMATIX_ENCODER_URL", "CYMATIX_CONFIG", "CYMATIX_GENOME_PATH"):
        env.pop(k, None)
    env.update({"PYTHONHASHSEED": "0", "PYTHONUTF8": "1", "PYTHONPATH": str(WT),
                "CYMATIX_DISABLE_LEARN": "1", "CYMATIX_SQLITE_CACHE_SIZE": "-12582912"})
    missing = [n for n, (db, sub, res, gold) in BEDS.items()
               for p in (db, D / sub / res, D / sub / gold) if not Path(p).exists()]
    if missing:
        raise SystemExit(f"missing inputs: {sorted(set(missing))}")
    order = [n for n in BEDS if n != "erb_947k"] + ["erb_947k"]
    try:
        for name in order:
            if out_path(name).exists():
                continue
            db, sub, res, gold = BEDS[name]
            cmd = [sys.executable, "-P", str(D / "erb" / "know_abstain_replay.py"), "--genome", db,
                   "--resolved", str(D / sub / res), "--gold", str(D / sub / gold), "--limit", "0", "--k", "12",
                   "--arms", "postflip_default", "--config", str(WT / "cymatix.toml"), "--stamp", "2026-10-08",
                   "--ce-model", CE, "--out", str(out_path(name))]
            t0 = time.time()
            with open(RUN / f"stage_{name}.log", "w", encoding="utf-8") as fh:
                rc = subprocess.run(cmd, cwd=str(WT), env=env, stdout=fh, stderr=subprocess.STDOUT,
                                    creationflags=NO_WINDOW).returncode
            with open(RUN / "progress.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"bed": name, "rc": rc, "wall_s": round(time.time() - t0, 1),
                                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        (RUN / "DONE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
