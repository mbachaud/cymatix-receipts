"""Copy BRIGHT + pooled multi-hop receipts into cymatix-receipts; write SUMMARY.json + TABLE.md."""
import glob, json, shutil
from pathlib import Path
B = Path("/home/user/bench"); S = B / "out_nosplade"
DEST = Path("/home/user/cymatix-receipts/untracked/benchmarks/dogfood/receipts/bright_multihop_linux_vm_2026-11-03")
PAPER = {"biology": .189, "earth_science": .272, "economics": .149, "psychology": .125, "robotics": .136,
         "stackoverflow": .184, "sustainable_living": .150, "leetcode": .244, "pony": .079, "aops": .062,
         "theoremqa_questions": .104, "theoremqa_theorems": .049}
bm = json.load(open(S / "bright_bm25_same_corpus_2026-11-03.json"))
rows = {"bright": [], "multihop": []}
for f in sorted(glob.glob(str(S / "beir_ndcg_beir_*.json"))):
    tag = json.load(open(f))["tag"]
    if not (tag.startswith("beir_bright_") or tag.startswith("beir_mh_")): continue
    d = DEST / tag; d.mkdir(parents=True, exist_ok=True)
    for pat in (f"beir_ndcg_{tag}_*.json", f"ladder_{tag}_seed0_*.json", f"needles_resolved_{tag}_full.json",
                f"gold_by_needle_{tag}.json", f"mh_score_{tag}_*.json"):
        for g in glob.glob(str(S / pat)): shutil.copy(g, d)
    if (S / f"bed_manifest_{tag}.json").exists(): shutil.copy(S / f"bed_manifest_{tag}.json", d / "bed_manifest.json")
    ex = B / "work/benchmarks/dogfood" / tag / f"excluded_{tag}.json"
    if ex.exists(): shutil.copy(ex, d)
    log = S / f"stage_build_{tag}.log"
    if log.exists():
        tail = [l for l in log.read_text(errors="replace").splitlines() if "INFO" in l][-12:]
        (d / "build_log_tail.txt").write_text("\n".join(tail) + "\n")
    nd = json.load(open(f)); m = nd["mean_over_ran"]
    if tag.startswith("beir_bright_"):
        dom = tag.removeprefix("beir_bright_")
        rows["bright"].append({"domain": dom, "n": len(nd["per_query"]), "cymatix_ndcg@10": round(m["ndcg@10"], 4),
                               "cymatix_recall@100": round(m["recall@100"], 4), "paper_bm25_ndcg@10": PAPER[dom], **bm[dom]})
    else:
        mh = json.load(open(glob.glob(str(S / f"mh_score_{tag}_*.json"))[0]))["summary"]
        rows["multihop"].append({"set": tag.removeprefix("beir_mh_"), "ndcg@10": round(m["ndcg@10"], 4), **mh})
shutil.copy(S / "bright_bm25_same_corpus_2026-11-03.json", DEST)
tools = DEST / "tools"; tools.mkdir(exist_ok=True)
for t in ("bright_to_beir.py", "multihop_to_beir.py", "mh_score.py", "bright_bm25.py", "beir_ndcg_multi.py"):
    shutil.copy(B / "tools" / t, tools)
shutil.copy(B / "run_beir_linux.py", DEST); shutil.copy(Path(__file__), DEST / "package.py")
(DEST / "SUMMARY.json").write_text(json.dumps({"engine_commit": "bd3c541f (beta 091dab94 + PR #534)", **rows}, indent=1) + "\n")
br = sorted(rows["bright"], key=lambda r: list(PAPER).index(r["domain"]))
t = ["| BRIGHT domain | n | Cymatix nDCG@10 | paper BM25 | bm25s same-corpus | Cymatix R@100 | bm25s R@100 |", "|---|---|---|---|---|---|---|"]
t += [f"| {r['domain']} | {r['n']} | {r['cymatix_ndcg@10']:.4f} | {r['paper_bm25_ndcg@10']:.3f} | {r['bm25_ndcg@10']:.4f} | {r['cymatix_recall@100']:.4f} | {r['bm25_recall@100']:.4f} |" for r in br]
avg = lambda k: sum(r[k] for r in br) / len(br)
t += [f"| **mean** | | {avg('cymatix_ndcg@10'):.4f} | {avg('paper_bm25_ndcg@10'):.3f} | {avg('bm25_ndcg@10'):.4f} | {avg('cymatix_recall@100'):.4f} | {avg('bm25_recall@100'):.4f} |", ""]
t += ["| multi-hop set | n | nDCG@10 | all@10 | BM25 all@10 | all delivered (12) | BM25 all@12 | frac delivered | BM25 frac@12 | any delivered | all@100* | BM25 all@100 | packet chars (median) |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
t += [f"| {r['set']} | {r['n']} | {r['ndcg@10']:.4f} | {r['all@10']:.4f} | {r['bm25_all@10']:.4f} | {r['all_delivered']:.4f} | {r['bm25_all@12']:.4f} | {r['frac_delivered']:.4f} | {r['bm25_frac@12']:.4f} | {r['any_delivered']:.4f} | {r['all@100']:.4f} | {r['bm25_all@100']:.4f} | {r['delivered_chars_median']:.0f} |" for r in rows["multihop"]]
(DEST / "TABLE.md").write_text("\n".join(t) + "\n"); print("\n".join(t))
