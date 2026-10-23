"""jev_erb_packet_know.py — Jev know/miss + chunk filtering on an ERB bed.

EXPERIMENTAL. The ERB follow-up to ``jev_239b_packet_know.py`` (same typed
question sheet, same chunk/packet questions, same incoming rankings). Jev is
a proprietary hosted API, not part of the cymatix pipeline; nothing here
changes retrieval.

Labels, computed locally and never sent to Jev:

* packet ``truth_know`` — at least one of the needle's resolved gold genes is
  in the delivered packet (the ladder's ``delivered_gold`` basis). ERB has no
  held-out needles, so a "miss" here is a cymatix delivery miss.
* chunk ``is_gold`` — the delivered gene is one of the needle's gold genes
  (gene grain; the bank carries no answer strings, so a gold gene that only
  partly answers still counts, and a non-gold gene that answers does not).

The ERB ``question_type`` (basic, semantic, ...) is reported per type and is
NOT sent; Jev types the question itself from the sheet, and receives the
cymatix query-classifier class as an incoming ranking.

Resumable: each finished needle (row, chunks, raw Jev responses) is appended
to ``<out>.progress.jsonl``; a rerun skips finished needles. ``<out>.lock``
holds the runner PID.

Usage::

    PYTHONHASHSEED=0 python benchmarks/dogfood/jev/jev_erb_packet_know.py \\
        --bed F:/tmp/grain_erb_full_c4000_2026-10-18/erb_full_c4000_lean.db \\
        --epoch 1792397919 --out <receipt.json> [--limit 3] [--dry]

Ablation (same packets, Jev sees no cymatix rankings)::

    PYTHONHASHSEED=0 python benchmarks/dogfood/jev/jev_erb_packet_know.py \\
        --bed <same bed> --no-incoming --packets-from <with-rankings receipt.json> \\
        --out <ablation receipt.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from jev_239b_packet_know import (  # noqa: E402
    MODEL, REPO_ROOT, SHEET, auroc, chunk_questions, confusion, git, jev_call,
    packet_questions, qtype_questions,
)

MAX_CHUNK_CHARS = 60_000    # well under Jev's ~150k-char per-question budget
DEFAULT_PROFILE = "benchmarks/dogfood/grain_ladder/configs/grain_c4000_classcap.toml"
DEFAULT_NEEDLES = "benchmarks/dogfood/erb/needles_resolved_grain4000_full.json"
DEFAULT_GOLD = "benchmarks/dogfood/erb/gold_by_needle_grain4000.json"
DEFAULT_LADDER = "F:/tmp/grain_erb_full_c4000_2026-10-18/ladder_erb_full_c4000_classcap_2026-10-17.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ladder_delivered(path: Path) -> dict:
    """needle -> {delivered_gold, delivered_gene_ids} from the ladder's first arm."""
    if not path.exists():
        return {}
    lad = json.loads(path.read_text(encoding="utf-8"))
    rows = next((a["per_query"] for a in lad.get("arms", [])
                 if isinstance(a, dict) and a.get("per_query")), [])
    return {r["needle"]: {"delivered_gold": r.get("delivered_gold"),
                          "ids": r.get("delivered_gene_ids")} for r in rows}


def summarize(needle_rows: list, chunks: list, ladder: dict) -> dict:
    out = {"needles": len(needle_rows), "chunks": len(chunks)}
    truth = [r["truth_know"] for r in needle_rows]
    jev_p = [r["jev_packet_answers"] for r in needle_rows]
    jev_maxchunk = [r["jev_max_chunk_answers"] for r in needle_rows]
    cym_conf = [r["cymatix"]["know_confidence"] or 0.0 for r in needle_rows]
    cym_top = [r["cymatix"]["top_score"] for r in needle_rows]
    out["know_miss"] = {
        "truth_know": sum(truth), "truth_miss": len(truth) - sum(truth),
        "auroc_jev_packet": auroc(jev_p, truth),
        "auroc_jev_max_chunk": auroc(jev_maxchunk, truth),
        "auroc_cymatix_know_confidence": auroc(cym_conf, truth),
        "auroc_cymatix_top_score": auroc(cym_top, truth),
        "cymatix_contract": confusion(
            [r["cymatix"]["block"] == "know" for r in needle_rows], truth),
        "cymatix_blocks": {b: sum(r["cymatix"]["block"] == b for r in needle_rows)
                           for b in ("know", "miss", "none")},
        "jev_packet_at": {str(t): confusion([p >= t for p in jev_p], truth)
                          for t in (0.3, 0.5, 0.7)},
        "jev_max_chunk_at_0.5": confusion([p >= 0.5 for p in jev_maxchunk], truth),
    }
    by_type = {}
    for qt in sorted({r["erb_type"] for r in needle_rows}):
        rs = [r for r in needle_rows if r["erb_type"] == qt]
        ks = [r for r in rs if r["truth_know"]]
        ms = [r for r in rs if not r["truth_know"]]
        by_type[qt] = {
            "n": len(rs), "truth_know": len(ks),
            "cymatix_know": sum(r["cymatix"]["block"] == "know" for r in rs),
            "jev_packet_mean_know": round(sum(r["jev_packet_answers"] for r in ks) / len(ks), 3) if ks else None,
            "jev_packet_mean_miss": round(sum(r["jev_packet_answers"] for r in ms) / len(ms), 3) if ms else None,
            "auroc_jev_packet": auroc([r["jev_packet_answers"] for r in rs],
                                      [r["truth_know"] for r in rs]),
            "jev_at_0.5_accuracy": confusion([r["jev_packet_answers"] >= 0.5 for r in rs],
                                             [r["truth_know"] for r in rs])["accuracy"],
        }
    out["by_erb_type"] = by_type
    out["qtype_jev"], out["qtype_cymatix_classifier"] = {}, {}
    for r in needle_rows:
        out["qtype_jev"][r["qtype"]] = out["qtype_jev"].get(r["qtype"], 0) + 1
        c = r["cymatix"]["classifier"]
        out["qtype_cymatix_classifier"][c] = out["qtype_cymatix_classifier"].get(c, 0) + 1

    if chunks:
        ys = [c["is_gold"] for c in chunks]
        out["chunk_filter"] = {
            "positives": sum(ys),
            "auroc_answers": auroc([c["jev"]["answers"] for c in chunks], ys),
            "auroc_typed": auroc([c["jev"]["typed"] for c in chunks], ys),
            "auroc_relevance": auroc([c["jev"]["relevance"] for c in chunks], ys),
            "auroc_cymatix_score": auroc([c["cymatix_score"] for c in chunks], ys),
            "auroc_cymatix_inverse_rank": auroc([-c["rank"] for c in chunks], ys),
        }
        gold_needles = {r["needle"] for r in needle_rows if r["truth_know"]}
        sims = []
        for t in (0.3, 0.5, 0.7):
            kept = [c for c in chunks if c["jev"]["answers"] >= t]
            retained = {c["needle"] for c in kept if c["is_gold"]}
            sims.append({
                "threshold": t,
                "chunks_kept": len(kept),
                "packet_reduction": round(1 - len(kept) / len(chunks), 3),
                "precision_gold": round(sum(c["is_gold"] for c in kept) / len(kept), 3) if kept else None,
                "needles_gold_delivered": len(gold_needles),
                "needles_gold_retained": len(retained),
                "chars_kept_frac": round(sum(c["chars"] for c in kept)
                                         / max(sum(c["chars"] for c in chunks), 1), 3),
            })
        out["chunk_filter"]["filter_sim"] = sims

    rr_cym, rr_jev = [], []
    for r in needle_rows:
        if not r["truth_know"]:
            continue
        cs = [c for c in chunks if c["needle"] == r["needle"]]
        order = sorted(cs, key=lambda c: (-c["jev"]["answers"], c["rank"]))
        jev_rank = next(i for i, c in enumerate(order, 1) if c["is_gold"])
        rr_cym.append(1 / r["gold_rank"])
        rr_jev.append(1 / jev_rank)
    if rr_cym:
        out["gold_ranking"] = {
            "n": len(rr_cym),
            "mrr_cymatix": round(sum(rr_cym) / len(rr_cym), 3),
            "mrr_jev_rerank": round(sum(rr_jev) / len(rr_jev), 3),
            "top1_cymatix": sum(x == 1 for x in rr_cym),
            "top1_jev_rerank": sum(x == 1 for x in rr_jev),
        }

    if ladder:
        both = [r for r in needle_rows if r["needle"] in ladder]
        lg = {r["needle"]: bool(ladder[r["needle"]]["delivered_gold"]) for r in both}
        out["paired_vs_ladder"] = {
            "n": len(both),
            "delivered_gold_same": sum(r["truth_know"] == lg[r["needle"]] for r in both),
            "this_only": sum(r["truth_know"] and not lg[r["needle"]] for r in both),
            "ladder_only": sum((not r["truth_know"]) and lg[r["needle"]] for r in both),
            "delivered_ids_identical": sum(r.get("delivered_ids") == ladder[r["needle"]]["ids"]
                                           for r in both),
        }
    return out


def load_progress(path: Path):
    rows, chunks, cache = [], [], {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            rows.append(rec["row"])
            chunks.extend(rec["chunks"])
            cache.update(rec["raw"])
    return rows, chunks, cache


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epoch", default=None, help="CYMATIX_SCORING_EPOCH to pin")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--needles", default=DEFAULT_NEEDLES)
    ap.add_argument("--gold", default=DEFAULT_GOLD)
    ap.add_argument("--ladder", default=DEFAULT_LADDER)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry", action="store_true", help="packets only, no Jev calls, nothing written")
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--no-incoming", action="store_true",
                    help="ablation: send Jev no cymatix rankings (no query class, rank, fused "
                         "score or know/miss block) and shuffle packet order per needle")
    ap.add_argument("--packets-from", default=None,
                    help="reuse delivered packets + cymatix fields from a prior receipt instead "
                         "of re-running retrieval; chunk text is read from --bed read-only")
    args = ap.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        print("ERROR: run with PYTHONHASHSEED=0", file=sys.stderr)
        return 2
    out_path = Path(args.out)
    progress = out_path.with_suffix(".progress.jsonl")
    lock = out_path.with_suffix(".lock")
    ladder = ladder_delivered(Path(args.ladder))

    if args.rescore:
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev["summary"] = summarize(prev["needles"], prev["chunks"], ladder)
        out_path.write_text(json.dumps(prev, indent=1), encoding="utf-8")
        print(json.dumps(prev["summary"], indent=1))
        return 0

    key_var = next((v for v in ("JEV_API_KEY", "TYPESAFE_API_KEY") if os.environ.get(v)), None)
    if not args.dry and key_var is None:
        print("ERROR: neither JEV_API_KEY nor TYPESAFE_API_KEY is set", file=sys.stderr)
        return 2
    api_key = os.environ.get(key_var) if key_var else None

    if not args.dry:
        if lock.exists():
            other = int(lock.read_text().strip() or 0)
            if other and pid_alive(other):
                print(f"ERROR: {lock} held by live PID {other}", file=sys.stderr)
                return 2
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(os.getpid()))

    bed = Path(args.bed)
    profile = (REPO_ROOT / args.profile).resolve()
    prior_rows, prior_scores, ro = {}, {}, None
    if args.packets_from:
        # Replay: the packets were already delivered (and parity-checked against
        # the ladder) by a prior run of this harness; only the Jev side reruns.
        prior = json.loads(Path(args.packets_from).read_text(encoding="utf-8"))
        prior_rows = {r["needle"]: r for r in prior["needles"]}
        prior_scores = {(c["needle"], c["gene_id"]): c for c in prior["chunks"]}
        ro = sqlite3.connect(f"file:{bed}?mode=ro", uri=True)
        n_genes = ro.execute("SELECT COUNT(*) FROM genes").fetchone()[0]
        loaded_cfg = {**prior["loaded_config"], "packets_from": args.packets_from,
                      "packets_from_commit": prior.get("commit")}
        print(f"replaying {len(prior_rows)} packets from {args.packets_from}; bed genes={n_genes}",
              flush=True)
    else:
        os.environ["CYMATIX_DISABLE_LEARN"] = "1"
        os.environ["CYMATIX_GENOME_PATH"] = str(bed)
        os.environ["CYMATIX_LEAN_INDEXES"] = "1"
        os.environ.pop("CYMATIX_ENCODER_URL", None)
        if args.epoch:
            os.environ["CYMATIX_SCORING_EPOCH"] = str(args.epoch)
        from cymatix_context.config import load_config  # noqa: E402
        from cymatix_context.context_manager import CymatixContextManager  # noqa: E402
        from cymatix_context.retrieval.query_classifier import classify_query  # noqa: E402
        from cymatix_context.server.helpers import _compute_know_or_miss_block  # noqa: E402

        cfg = load_config(str(profile))
        cfg.genome.path = str(bed)
        mgr = CymatixContextManager(cfg)
        n_genes = mgr.genome.conn.execute("SELECT COUNT(*) FROM genes").fetchone()[0]
    loaded_cfg = loaded_cfg if args.packets_from else {
        "profile": args.profile,
        "genome.path": cfg.genome.path,
        "retrieval.fusion_mode": cfg.retrieval.fusion_mode,
        "retrieval.rrf_k": cfg.retrieval.rrf_k,
        "retrieval.dense_embedding_enabled": cfg.retrieval.dense_embedding_enabled,
        "budget.max_genes_per_turn": cfg.budget.max_genes_per_turn,
        "budget.expression_tokens": cfg.budget.expression_tokens,
        "budget.min_delivered_docs": cfg.budget.min_delivered_docs,
        "budget.classifier_cap_ref_chars": getattr(cfg.budget, "classifier_cap_ref_chars", None),
        "budget.abstain_enabled": getattr(cfg.budget, "abstain_enabled", None),
        "know.emit_floor": getattr(cfg.know, "emit_floor", None),
        "ribosome.backend": cfg.ribosome.backend,
        "env.CYMATIX_SCORING_EPOCH": os.environ.get("CYMATIX_SCORING_EPOCH"),
        "env.CYMATIX_LEAN_INDEXES": os.environ.get("CYMATIX_LEAN_INDEXES"),
        "env.CYMATIX_ENCODER_URL": os.environ.get("CYMATIX_ENCODER_URL"),
        "k": args.k,
    }
    print(f"bed: {bed} genes={n_genes}; loaded config:", json.dumps(loaded_cfg), flush=True)

    needles_path = REPO_ROOT / args.needles
    gold_path = REPO_ROOT / args.gold
    needles = json.loads(needles_path.read_text(encoding="utf-8"))["needles"]
    gold_by = {k: set(v) for k, v in json.loads(gold_path.read_text(encoding="utf-8")).items()}
    if args.limit:
        needles = needles[: args.limit]

    needle_rows, chunks, cache = ([], [], {}) if args.dry else load_progress(progress)
    done = {r["needle"] for r in needle_rows}
    if done:
        print(f"resuming: {len(done)} needles done in {progress}", flush=True)

    last_call = [0.0]
    jev_models = {cache[k].get("model") for k in cache}
    t0 = time.monotonic()
    for i, nd in enumerate(needles, 1):
        name, q = nd["name"], nd["query"]
        if name in done:
            continue
        tq = time.monotonic()
        gold = gold_by.get(name, set())
        delivered = []
        if args.packets_from:
            pr = prior_rows[name]
            ids, cym = list(pr["delivered_ids"]), dict(pr["cymatix"])
            for rank, gid in enumerate(ids, 1):
                pc = prior_scores.get((name, gid))
                if pc is None:   # the prior run could not fetch this gene either
                    continue
                src, content = ro.execute("SELECT source_id, content FROM genes WHERE gene_id=?",
                                          (gid,)).fetchone()
                text = (content or "")[:MAX_CHUNK_CHARS]
                if len(text) != pc["chars"]:
                    raise RuntimeError(f"{name}/{gid}: replayed text {len(text)} chars, "
                                       f"prior run saw {pc['chars']}")
                delivered.append({"rank": rank, "gene_id": gid, "source": src or "",
                                  "text": text, "score": pc["cymatix_score"],
                                  "is_gold": gid in gold})
        else:
            window = mgr.build_context(q, read_only=True, ignore_delivered=True, max_genes=args.k)
            block = _compute_know_or_miss_block(cymatix=mgr, window=window, query=q)
            ids = list(window.expressed_gene_ids)
            scores = window.retrieval_scores or {}
            is_know = block is not None and getattr(block, "found", False) is True
            cym = {
                "classifier": classify_query(q).cls,
                "block": "know" if is_know else ("miss" if block is not None else "none"),
                "know_confidence": getattr(block, "confidence", None) if is_know else None,
                "miss_reason": getattr(block, "reason", None) if not is_know and block is not None else None,
                "top_score": float(getattr(block, "top_score", 0.0) or 0.0),
                "score_gap": getattr(block, "score_gap", None),
                "delivered": len(ids),
                "build_s": round(time.monotonic() - tq, 2),
            }
            for rank, gid in enumerate(ids, 1):
                gene = mgr.genome.get_doc(gid)
                if gene is None:
                    continue
                delivered.append({"rank": rank, "gene_id": gid, "source": gene.source_id or "",
                                  "text": (gene.content or "")[:MAX_CHUNK_CHARS],
                                  "score": round(float(scores.get(gid, 0.0)), 4),
                                  "is_gold": gid in gold})
        gold_rank = next((d["rank"] for d in delivered if d["is_gold"]), None)
        row = {"needle": name, "erb_type": nd.get("question_type"), "query": q,
               "truth_know": gold_rank is not None, "gold_rank": gold_rank,
               "gold_genes": len(gold), "delivered_ids": ids, "cymatix": cym}
        if args.dry:
            lad = ladder.get(name, {})
            print(f"[{i}/{len(needles)}] {name} {row['erb_type']:24s} cls={cym['classifier']:10s} "
                  f"{cym['block']:4s} reason={cym['miss_reason']} conf={cym['know_confidence']} "
                  f"delivered={len(ids)} gold_rank={gold_rank} ladder_gold={lad.get('delivered_gold')} "
                  f"ids_same={lad.get('ids') == ids} "
                  f"chars={sum(len(d['text']) for d in delivered)} build_s={cym['build_s']}", flush=True)
            continue

        raw = {}

        def call(key, state, questions):
            if key not in cache:
                cache[key] = jev_call(api_key, state, questions, last_call)
            raw[key] = cache[key]
            jev_models.add(cache[key].get("model"))
            return cache[key]["answers"]

        qt = call(f"{name}::qtype", {"question": q}, qtype_questions())["qtype"]
        qtype = qt["choice"]
        incoming = {"query_class": cym["classifier"], "delivered": len(delivered)}
        n_rows = []
        for d in delivered:
            state = {"question": q, "question_type": qtype,
                     "chunk": {"source": d["source"], "text": d["text"]}}
            if not args.no_incoming:
                state["retrieval"] = {**incoming, "rank": d["rank"], "fused_score": d["score"]}
            ans = call(f"{name}::{d['gene_id']}::{qtype}", state, chunk_questions(qtype))
            n_rows.append({"needle": name, "erb_type": row["erb_type"], "rank": d["rank"],
                           "gene_id": d["gene_id"], "cymatix_score": d["score"],
                           "is_gold": d["is_gold"], "chars": len(d["text"]),
                           "jev": {"answers": ans["answers"]["noul"],
                                   "typed": ans["typed"]["noul"],
                                   "relevance": ans["relevance"]["score"]}})
        contract = {"verdict": cym["block"], "confidence": cym["know_confidence"],
                    "miss_reason": cym["miss_reason"], "top_score": cym["top_score"],
                    "score_gap": cym["score_gap"]}
        if args.no_incoming:
            # Packet order is itself the cymatix ranking: shuffle it, seeded
            # per needle (random.Random(str) is independent of PYTHONHASHSEED).
            shuffled = list(delivered)
            random.Random(name).shuffle(shuffled)
            pstate = {"question": q, "question_type": qtype,
                      "packet": [{"source": d["source"], "text": d["text"]} for d in shuffled]}
        else:
            pstate = {"question": q, "question_type": qtype,
                      "retrieval": {**incoming, "know_miss": contract},
                      "packet": [{"rank": d["rank"], "fused_score": d["score"],
                                  "source": d["source"], "text": d["text"]} for d in delivered]}
        pk = call(f"{name}::packet::{qtype}", pstate, packet_questions())
        row.update({"qtype": qtype, "qtype_probs": qt.get("probabilities"),
                    "jev_packet_answers": pk["packet_answers"]["noul"],
                    "jev_max_chunk_answers": max((c["jev"]["answers"] for c in n_rows), default=0.0),
                    "needle_s": round(time.monotonic() - tq, 1)})
        needle_rows.append(row)
        chunks.extend(n_rows)
        with open(progress, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"row": row, "chunks": n_rows, "raw": raw}) + "\n")
        print(f"[{len(needle_rows)}/{len(needles)}] {name} {row['erb_type']:24s} {cym['block']:4s} "
              f"gold_rank={gold_rank} jev_packet={row['jev_packet_answers']:.3f} "
              f"build_s={cym['build_s']} needle_s={row['needle_s']}", flush=True)

    if args.dry:
        return 0

    receipt = {
        "experimental": True,
        "harness": "benchmarks/dogfood/jev/jev_erb_packet_know.py",
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "behind_master": git("rev-list", "--count", "HEAD..origin/master"),
        "dirty": bool(git("status", "--porcelain")),
        "bed": {"path": str(bed), "bytes": bed.stat().st_size, "genes": n_genes},
        "needles_file": args.needles, "needles_sha256": sha256_file(needles_path),
        "gold_file": args.gold, "gold_sha256": sha256_file(gold_path),
        "needles_scored": len(needle_rows),
        "profile_sha256": sha256_file(profile),
        "ladder_receipt": args.ladder,
        "arm": "no_incoming" if args.no_incoming else "with_incoming",
        "loaded_config": loaded_cfg,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "api_key_var": key_var,
        "jev_model_requested": MODEL,
        "jev_models": sorted(m for m in jev_models if m),
        "jev_input_tokens": sum(v.get("usage", {}).get("input_tokens", 0) for v in cache.values()),
        "wall_s_this_session": round(time.monotonic() - t0, 1),
        "sheet": {k: list(v) for k, v in SHEET.items()},
        "summary": summarize(needle_rows, chunks, ladder),
        "needles": needle_rows,
        "chunks": chunks,
        "raw_cache": cache,
    }
    out_path.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    lock.unlink(missing_ok=True)
    print(json.dumps(receipt["summary"], indent=1))
    print(f"receipt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
