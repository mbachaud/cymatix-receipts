"""Paired comparison of two jev_erb_packet_know receipts on the same packets.

Usage: python -P compare_jev_arms.py --a <with-rankings.json> --b <no-incoming.json> --out <json>

Needles join by name; both arms must have scored the same delivered ids
(asserted). Reports per-arm know/miss and chunk AUROCs, a paired bootstrap
95% CI on the packet AUROC delta (b - a), the 0.5-threshold correctness flips
(McNemar counts), per-ERB-type packet AUROC, and the gold rerank MRR.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev_239b_packet_know import auroc  # noqa: E402


def mrr(rows, chunks):
    by = {}
    for c in chunks:
        by.setdefault(c["needle"], []).append(c)
    rr = []
    for r in rows:
        if r["truth_know"]:
            order = sorted(by[r["needle"]], key=lambda c: (-c["jev"]["answers"], c["rank"]))
            rr.append(1 / next(i for i, c in enumerate(order, 1) if c["is_gold"]))
    return round(sum(rr) / len(rr), 3), sum(x == 1 for x in rr)


def arm_stats(rows, chunks):
    truth = [r["truth_know"] for r in rows]
    p = [r["jev_packet_answers"] for r in rows]
    ys = [c["is_gold"] for c in chunks]
    m, top1 = mrr(rows, chunks)
    return {
        "auroc_packet": auroc(p, truth),
        "auroc_max_chunk": auroc([r["jev_max_chunk_answers"] for r in rows], truth),
        "acc_packet_0.5": round(sum((x >= 0.5) == t for x, t in zip(p, truth)) / len(rows), 3),
        "fp_0.5": sum(x >= 0.5 and not t for x, t in zip(p, truth)),
        "fn_0.5": sum(x < 0.5 and t for x, t in zip(p, truth)),
        "mean_p_know": round(sum(x for x, t in zip(p, truth) if t) / max(sum(truth), 1), 3),
        "mean_p_miss": round(sum(x for x, t in zip(p, truth) if not t) / max(len(truth) - sum(truth), 1), 3),
        "chunk_auroc_answers": auroc([c["jev"]["answers"] for c in chunks], ys),
        "chunk_auroc_typed": auroc([c["jev"]["typed"] for c in chunks], ys),
        "chunk_auroc_relevance": auroc([c["jev"]["relevance"] for c in chunks], ys),
        "rerank_mrr": m, "rerank_top1": top1,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args()
    A = json.loads(Path(args.a).read_text(encoding="utf-8"))
    B = json.loads(Path(args.b).read_text(encoding="utf-8"))
    ra = {r["needle"]: r for r in A["needles"]}
    rb = {r["needle"]: r for r in B["needles"]}
    names = sorted(set(ra) & set(rb))
    for n in names:
        assert ra[n]["delivered_ids"] == rb[n]["delivered_ids"], f"{n}: packets differ"
        assert ra[n]["truth_know"] == rb[n]["truth_know"], n
    rows_a = [ra[n] for n in names]
    rows_b = [rb[n] for n in names]
    keep = set(names)
    ch_a = [c for c in A["chunks"] if c["needle"] in keep]
    ch_b = [c for c in B["chunks"] if c["needle"] in keep]

    truth = [r["truth_know"] for r in rows_a]
    pa = [r["jev_packet_answers"] for r in rows_a]
    pb = [r["jev_packet_answers"] for r in rows_b]
    rng = random.Random(239)
    deltas = []
    for _ in range(args.boot):
        idx = [rng.randrange(len(names)) for _ in names]
        t = [truth[i] for i in idx]
        da, db = auroc([pa[i] for i in idx], t), auroc([pb[i] for i in idx], t)
        if da is not None and db is not None:
            deltas.append(db - da)
    deltas.sort()
    ca = [(x >= 0.5) == t for x, t in zip(pa, truth)]
    cb = [(x >= 0.5) == t for x, t in zip(pb, truth)]

    by_type = {}
    for qt in sorted({r["erb_type"] for r in rows_a}):
        ix = [i for i, r in enumerate(rows_a) if r["erb_type"] == qt]
        t = [truth[i] for i in ix]
        by_type[qt] = {"n": len(ix),
                       "auroc_a": auroc([pa[i] for i in ix], t),
                       "auroc_b": auroc([pb[i] for i in ix], t)}

    out = {
        "a": {"receipt": args.a, "arm": A.get("arm", "with_incoming"), "commit": A.get("commit")},
        "b": {"receipt": args.b, "arm": B.get("arm"), "commit": B.get("commit")},
        "n_needles": len(names), "truth_know": sum(truth),
        "packets_identical": True,
        "stats_a": arm_stats(rows_a, ch_a),
        "stats_b": arm_stats(rows_b, ch_b),
        "packet_auroc_delta_b_minus_a": {
            "point": round(auroc(pb, truth) - auroc(pa, truth), 4),
            "boot_ci95": [round(deltas[int(0.025 * len(deltas))], 4),
                          round(deltas[int(0.975 * len(deltas)) - 1], 4)],
            "boot_n": len(deltas), "seed": 239,
        },
        "flips_at_0.5": {"a_right_b_wrong": sum(x and not y for x, y in zip(ca, cb)),
                         "a_wrong_b_right": sum(y and not x for x, y in zip(ca, cb))},
        "mean_abs_packet_diff": round(sum(abs(x - y) for x, y in zip(pa, pb)) / len(names), 3),
        "by_erb_type": by_type,
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
