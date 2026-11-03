"""Linux port of benchmarks/dogfood/sweeps/run_beir_round1.py for the cloud VM.

Same stage order, args and child env as the Windows runner; only paths differ.
All outputs land under /home/user/bench so committed repo files are untouched.
Cold-bed gate is skipped (latency numbers are therefore warm-cache).
"""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path("/home/user/Cymatix-Context")
B = Path("/home/user/bench")
PULL = B / "pulls" / "beir"
CORPUS = B / "corpus"
WORK = B / "work"                       # cwd for emitter -> WORK/benchmarks/dogfood/<tag>
NOSPLADE = os.environ.get("NOSPLADE") == "1"
FLOOR = os.environ.get("FLOOR", "1")
SFX = ("_nosplade" if NOSPLADE else "") + ("" if FLOOR == "1" else f"_floor{FLOOR}")
OUT = B / ("out" + SFX)
STAMP = time.strftime("%Y-%m-%d")
D = ROOT / "benchmarks" / "dogfood"
TAGS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["beir_scifact", "beir_nfcorpus", "beir_arguana", "beir_scidocs", "beir_fiqa"]

ENV = dict(os.environ, PYTHONHASHSEED="0", PYTHONUTF8="1", PYTHONPATH=str(ROOT),
           CYMATIX_DISABLE_LEARN="1", CYMATIX_SQLITE_CACHE_SIZE="-12582912",
           CYMATIX_COVER_INDEX_AUTOBUILD="0")
ENV.pop("CYMATIX_ENCODER_URL", None); ENV.pop("CYMATIX_CONFIG", None)

EMIT = f"""
import sys, pathlib
sys.path.insert(0, {str(ROOT / 'scripts')!r})
import build_beir_corpus as m
m.PULL = pathlib.Path({str(PULL)!r}); m.CORPUS_BASE = pathlib.Path({str(CORPUS)!r})
raise SystemExit(m.main(sys.argv[1:]))
"""
BUILD = f"""
import sys
sys.path.insert(0, {str(ROOT / 'scripts')!r})
import build_fixture_matrix as m
tag = sys.argv[sys.argv.index('--profile') + 1]
if tag not in m.PROFILES: m.PROFILES[tag] = dict(m.PROFILES['beir_scifact'], label=tag)
m.PROFILES[tag]['min_file_bytes'] = int(__import__('os').environ.get('FLOOR', '1'))
m.PROFILES[tag]['roots'] = [{str(CORPUS)!r} + '/' + tag + '/corpus']
sys.argv = ['build_fixture_matrix.py'] + sys.argv[1:]
raise SystemExit(m.main())
"""

def run(name, cmd, cwd=ROOT, extra=None):
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(OUT / f"stage_{name}.log", "w") as fh:
        r = subprocess.run(cmd, cwd=cwd, env=dict(ENV, **(extra or {})), stdout=fh, stderr=subprocess.STDOUT)
    rec = {"stage": name, "rc": r.returncode, "wall_s": round(time.time() - t0, 1), "ts": time.strftime("%FT%T")}
    with open(OUT / "progress.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec, flush=True)
    return r.returncode

def do(tag):
    ds = tag.removeprefix("beir_")
    ds = {"trec_covid": "trec-covid", "webis_touche2020": "webis-touche2020"}.get(ds, ds)
    if ds.startswith("cqadupstack_"): ds = "cqadupstack/" + ds.split("_", 1)[1]
    bench = WORK / "benchmarks" / "dogfood" / tag
    corpus = CORPUS / tag / "corpus"
    bed = B / ("beds" + SFX) / f"{tag}_bed"; db = bed / f"{tag}.db"
    ladder = OUT / f"ladder_{tag}_seed0_{STAMP}.json"; ndcg = OUT / f"beir_ndcg_{tag}_{STAMP}.json"
    WORK.mkdir(parents=True, exist_ok=True)
    if not (bench / f"needles_{tag}.json").exists():
        if run(f"emit_{tag}", [sys.executable, "-c", EMIT, "--dataset", ds, "--tag", tag], cwd=WORK): return False
    exsrc = PULL / ds / "excluded.json"
    if exsrc.exists() and not (bench / f"excluded_{tag}.json").exists():
        sys.path.insert(0, str(ROOT / "scripts")); import build_beir_corpus as bbc
        ex = json.loads(exsrc.read_text())
        (bench / f"excluded_{tag}.json").write_text(json.dumps({f"{tag}_{q}": [bbc.rel_path(d) for d in ds_] for q, ds_ in ex.items()}))
    if not (db.exists() and (bed / "manifest.json").exists()):
        if run(f"build_{tag}", [sys.executable, "-c", BUILD, "--profile", tag, "--out-dir", str(bed),
                                "--parallel", "--workers", "4"],
               extra={"CYMATIX_BFM_HUB_CUTOFF": "200", "CYMATIX_BFM_DENSE_BACKFILL": "0", **({"CYMATIX_BFM_SPLADE": "0"} if NOSPLADE else {})}): return False
    resolved = OUT / f"needles_resolved_{tag}_full.json"
    if not resolved.exists() and (bench / resolved.name).exists(): (bench / resolved.name).unlink(); (bench / f"gold_by_needle_{tag}.json").unlink(missing_ok=True)
    if not resolved.exists():
        if run(f"resolve_{tag}", [sys.executable, "-P", str(ROOT / "scripts" / "resolve_bench_needles.py"),
               "--tag", tag, "--db", str(db), "--bench-dir", str(bench), "--corpus-root", str(corpus),
               "--min-file-bytes", FLOOR]): return False
        (bench / resolved.name).rename(resolved); import shutil; shutil.copy(bench / f"gold_by_needle_{tag}.json", OUT / f"gold_by_needle_{tag}.json")
    if not ladder.exists():
        if run(f"ladder_{tag}", [sys.executable, "-P", str(D / "erb" / "ablation_ladder.py"), "--cover-index", "off",
               "--genome", str(db), "--resolved", str(resolved), "--gold", str(OUT / f"gold_by_needle_{tag}.json"),
               "--limit", "0", "--k", "12", "--arms", "baseline", "--config", str(ROOT / "cymatix.toml"),
               "--per-query", "--rank-dump", "200", "--stamp", STAMP, "--out", str(ladder)]): return False
    if not ndcg.exists():
        if run(f"ndcg_{tag}", [sys.executable, "-P", str(B / "tools" / "beir_ndcg_multi.py"), "--tag", tag,
               "--receipt", str(ladder), "--db", str(db), "--bench-dir", str(bench),
               "--corpus-root", str(corpus), "--out", str(ndcg)]): return False
    mh = OUT / f"mh_score_{tag}_{STAMP}.json"
    if tag.startswith("beir_mh_") and not mh.exists():
        if run(f"mhscore_{tag}", [sys.executable, str(B / "tools" / "mh_score.py"), "--tag", tag, "--ladder", str(ladder),
               "--db", str(db), "--bench-dir", str(bench), "--corpus-root", str(corpus), "--out", str(mh)]): return False
    if (bed / "manifest.json").exists():
        import shutil; shutil.copy(bed / "manifest.json", OUT / f"bed_manifest_{tag}.json")
    if os.environ.get("CLEANUP") == "1":
        import shutil; shutil.rmtree(bed, ignore_errors=True); shutil.rmtree(CORPUS / tag, ignore_errors=True)
    return True

failed = [t for t in TAGS if not do(t)]
print("DONE failed=", failed, flush=True)
