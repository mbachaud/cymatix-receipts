import json,glob,sys
REF="/home/user/cymatix-receipts/untracked/benchmarks/dogfood/receipts/traced_sweep_2026-10-11"
print(f"{'bed':30} {'ref nDCG@10':>11} {'VM nDCG@10':>10} {'R@10 ref/VM':>13} {'R@100 ref/VM':>14} per-query")
for f in sorted(glob.glob("/home/user/bench/out*/beir_ndcg_*.json")):
    b=json.load(open(f)); t=b['tag']
    r=glob.glob(f"{REF}/{t}/beir_ndcg_*.json")
    if not r: print(t,b['mean_over_ran'],"(no ref)"); continue
    a=json.load(open(r[0])); ma,mb=a['mean_over_ran'],b['mean_over_ran']
    def pq(x): p=x['per_query']; return {q.get('needle',q.get('name')):q.get('ndcg@10') for q in p} if isinstance(p,list) else {k:v.get('ndcg@10') if isinstance(v,dict) else v for k,v in p.items()}
    pa,pb=pq(a),pq(b); up=sum(1 for k in pa if (pb.get(k) or 0)>(pa[k] or 0)+1e-9); dn=sum(1 for k in pa if (pb.get(k) or 0)<(pa[k] or 0)-1e-9)
    tag=t+(" [splade-on]" if "/out/" in f else "")
    print(f"{tag:30} {ma['ndcg@10']:11.4f} {mb['ndcg@10']:10.4f} {ma['recall@10']:.4f}/{mb['recall@10']:.4f} {ma['recall@100']:.4f}/{mb['recall@100']:.4f} +{up}/-{dn} n={len(pb)}/{len(pa)}")
