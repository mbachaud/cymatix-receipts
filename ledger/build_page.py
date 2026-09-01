"""build_page.py -- render ledger/ledger.json as a single self-contained HTML page.

    python ledger/build_page.py            (from the clone root; writes ledger/ledger-page.html)

The page is the long-term results tracker: shipped-default delivered gold rate
per bed over time (with every measured arm as a faint mark), the graduation
ledger, the kill ledger, a per-bed status table, and the coverage gaps. All
numbers come from ledger.json; nothing is typed in here.
"""
import html
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "ledger.json"
OUT = HERE / "ledger-page.html"
REPO_URL = "https://github.com/mbachaud/cymatix-receipts"
MAIN_URL = "https://github.com/mbachaud/Cymatix-Context"

PANELS = [
    ("ERB 947k, the campaign bed", "erb", ["erb_blob_v09x_947k"]),
    ("ERB 829k", "erb", ["erb_blob_829k", "erb_829k_nosplade"]),
    ("ERB scale carves", "erb", ["erb_100k", "erb_250k", "erb_500k"]),
    ("EnronQA", "enronqa", ["enronqa_native", "enronqa_v2", "enronqa_padded"]),
    ("Dogfood", "dogfood", ["dogfood_sema_ab", "dogfood", "taggerdogfood_e2b"]),
]
SHORT = {
    "erb_blob_v09x_947k": "947k v09x", "erb_blob_829k": "829k blob", "erb_829k_nosplade": "829k nosplade",
    "erb_100k": "100k", "erb_250k": "250k", "erb_500k": "500k",
    "enronqa_native": "native 103k", "enronqa_v2": "v2 85k", "enronqa_padded": "padded",
    "dogfood_sema_ab": "dogfood (sema A/B)", "dogfood": "dogfood", "taggerdogfood_e2b": "tagger e2b",
}


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def fmt(x, nd=3):
    if x is None:
        return "·"
    try:
        return ("%." + str(nd) + "f") % float(x)
    except Exception:
        return esc(x)


def receipt_link(path):
    if not path:
        return "·"
    p = str(path)
    if p.startswith("mirror/"):
        url = MAIN_URL + "/blob/master/" + p[len("mirror/"):]
    else:
        url = REPO_URL + "/blob/main/" + p
    name = p.rsplit("/", 1)[-1]
    return '<a href="%s" title="%s">%s</a>' % (esc(url), esc(p), esc(name))


def main():
    L = json.loads(LEDGER.read_text(encoding="utf-8"))
    beds = {b["id"]: b for b in L["beds"]}
    ms = L["measurements"]

    # ---- plotted points: delivered basis, de-duplicated, degenerate zero rows dropped
    seen, points, dropped_zero = set(), [], 0
    for m in ms:
        d = m.get("delivered_gold_rate")
        if d is None:
            continue
        if d == 0 and (m.get("recall_at_12") in (0, 0.0)):
            dropped_zero += 1
            continue
        key = (m["bed_id"], m["date"], m.get("arm"), round(float(d), 4))
        if key in seen:
            continue
        seen.add(key)
        points.append({
            "bed": m["bed_id"], "date": m["date"], "arm": m.get("arm") or "", "d": round(float(d), 4),
            "r12": (round(float(m["recall_at_12"]), 4) if m.get("recall_at_12") is not None else None),
            "n": m.get("n"), "shipped": bool(m.get("shipped_default")), "receipt": m.get("receipt"),
            "campaign": m.get("campaign"),
        })
    plotted_ids = {b for _, _, ids in PANELS for b in ids}
    panels = []
    for title, fam, ids in PANELS:
        pts = [p for p in points if p["bed"] in ids]
        if not pts:
            continue
        panels.append({"title": title, "family": fam, "beds": ids,
                       "labels": {b: SHORT.get(b, b) for b in ids}, "points": pts})
    dates = sorted({p["date"] for p in points if p["bed"] in plotted_ids})

    # ---- latest shipped per bed
    latest = {}
    for p in points:
        if not p["shipped"]:
            continue
        cur = latest.get(p["bed"])
        if cur is None or p["date"] > cur["date"] or (p["date"] == cur["date"] and p["d"] > cur["d"]):
            latest[p["bed"]] = p
    counts_per_bed = defaultdict(int)
    for m in ms:
        counts_per_bed[m["bed_id"]] += 1

    # ---- tables
    def grad_rows():
        out = []
        for g in sorted(L["graduations"], key=lambda g: g["date"]):
            delta = ""
            if g.get("delivered_before") is not None and g.get("delivered_after") is not None:
                dd = float(g["delivered_after"]) - float(g["delivered_before"])
                cls = "up" if dd > 0 else ("down" if dd < 0 else "flat")
                delta = '<span class="delta %s">%+.3f</span>' % (cls, dd)
            out.append("<tr><td class=\"num\">%s</td><td class=\"lab\">%s</td><td>%s</td>"
                       "<td class=\"num\">%s → %s %s</td><td class=\"num\">%s</td><td>%s</td></tr>" % (
                           esc(g["date"]), esc(g["change"]), esc(g.get("bed_id") or "·"),
                           fmt(g.get("delivered_before")), fmt(g.get("delivered_after")), delta,
                           esc(g.get("paired") or "·"), receipt_link(g.get("receipt"))))
        return "\n".join(out)

    def kill_rows():
        out = []
        for k in sorted(L["kills"], key=lambda k: k["date"]):
            v = (k.get("verdict") or "KILL").upper()
            pill = {"KILL": "critical", "REFUTED": "critical", "NULL": "muted", "CORRECTED": "warning"}.get(v, "muted")
            out.append("<tr><td class=\"num\">%s</td><td class=\"lab\">%s</td><td>%s</td>"
                       "<td><span class=\"pill %s\" role=\"img\" aria-label=\"%s\">%s %s</span></td><td>%s</td><td>%s</td></tr>" % (
                           esc(k["date"]), esc(k["lever"]), esc(k.get("bed_id") or "·"), pill, esc(v),
                           {"critical": "✕", "warning": "△", "muted": "○"}[pill], esc(v),
                           esc(k.get("result") or ""), receipt_link(k.get("receipt"))))
        return "\n".join(out)

    def bed_rows():
        out = []
        order = sorted(beds.values(), key=lambda b: (b.get("family") or "", b["id"]))
        for b in order:
            lp = latest.get(b["id"])
            out.append("<tr><td class=\"lab\">%s</td><td>%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td>"
                       "<td class=\"num\">%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td></tr>" % (
                           esc(b["id"]), esc(b.get("family") or "·"),
                           ("{:,}".format(b["genes"]) if b.get("genes") else "·"),
                           esc(b.get("tagger_version") if b.get("tagger_version") is not None else "·"),
                           esc(b.get("ingest_c") if b.get("ingest_c") is not None else "·"),
                           (fmt(lp["d"]) if lp else "·"), (fmt(lp["r12"]) if lp and lp["r12"] is not None else "·"),
                           (esc(lp["date"]) if lp else "·"), counts_per_bed.get(b["id"], 0)))
        return "\n".join(out)

    def missing_rows():
        out = []
        for m in L["missing"]:
            out.append("<tr><td class=\"lab\">%s</td><td>%s</td><td>%s</td></tr>" % (
                esc(m.get("receipt")), esc(m.get("named_in") or ""), esc(m.get("note") or "")))
        return "\n".join(out)

    # ---- chart table view (a11y)
    def chart_table():
        out = []
        for p in sorted(points, key=lambda p: (p["bed"], p["date"], p["arm"])):
            if p["bed"] not in plotted_ids:
                continue
            out.append("<tr><td>%s</td><td class=\"num\">%s</td><td>%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td><td>%s</td></tr>" % (
                esc(p["bed"]), esc(p["date"]), esc(p["arm"]), fmt(p["d"]), fmt(p["r12"]) if p["r12"] is not None else "·",
                esc(p["n"] if p["n"] is not None else "·"), "shipped" if p["shipped"] else "arm"))
        return "\n".join(out)

    c = L["counts"]
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    src = L.get("source_commit", "")[:7]
    data = {"panels": panels, "dates": dates}

    page = TEMPLATE
    for k, v in {
        "{{GEN}}": esc(gen), "{{SRC}}": esc(src), "{{SRC_FULL}}": esc(L.get("source_commit", "")),
        "{{N_BEDS}}": str(c["beds"]), "{{N_MEAS}}": str(c["measurements"]), "{{N_KILLS}}": str(c["kills"]),
        "{{N_GRAD}}": str(c["graduations"]), "{{N_MISSING}}": str(c["missing"]),
        "{{N_POINTS}}": str(sum(len(p["points"]) for p in panels)), "{{N_ZERO}}": str(dropped_zero),
        "{{DATE_MIN}}": esc(dates[0] if dates else ""), "{{DATE_MAX}}": esc(dates[-1] if dates else ""),
        "{{GRAD_ROWS}}": grad_rows(), "{{KILL_ROWS}}": kill_rows(), "{{BED_ROWS}}": bed_rows(),
        "{{MISSING_ROWS}}": missing_rows(), "{{CHART_TABLE}}": chart_table(),
        "{{DATA_JSON}}": json.dumps(data, separators=(",", ":")).replace("</", "<\\/"),
        "{{REPO_URL}}": REPO_URL, "{{MAIN_URL}}": MAIN_URL,
    }.items():
        page = page.replace(k, v)
    OUT.write_text(page, encoding="utf-8")
    print("wrote", OUT, len(page), "bytes;", len(panels), "panels;", sum(len(p["points"]) for p in panels), "points")


TEMPLATE = r"""<title>Cymatix Receipt Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,600;12..96,700&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{
  color-scheme:light;
  --page:#f2f4f3; --surface:#fcfcfb; --sunk:#e9edeb;
  --ink:#101615; --ink-2:#4a5553; --muted:#7c8886; --rule:#dce1df; --grid:#e1e0d9; --axis:#c3c2b7;
  --accent:#2a78d6; --accent-soft:#e3eefb;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --good:#006300; --good-bg:#e4f2e4; --crit:#d03b3b; --crit-bg:#f8e3e3; --warn:#8a5f00; --warn-bg:#f7edd2; --mut-bg:#e9edeb;
  --ring:rgba(11,11,11,.10);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --page:#0d0d0d; --surface:#1a1a19; --sunk:#232322;
    --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781; --rule:#2c2c2a; --grid:#2c2c2a; --axis:#383835;
    --accent:#3987e5; --accent-soft:#16283d;
    --s1:#3987e5; --s2:#d95926; --s3:#199e70;
    --good:#0ca30c; --good-bg:#122412; --crit:#e66767; --crit-bg:#3a1c1c; --warn:#fab219; --warn-bg:#352a10; --mut-bg:#232322;
    --ring:rgba(255,255,255,.10);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --sunk:#232322;
  --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781; --rule:#2c2c2a; --grid:#2c2c2a; --axis:#383835;
  --accent:#3987e5; --accent-soft:#16283d;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --good:#0ca30c; --good-bg:#122412; --crit:#e66767; --crit-bg:#3a1c1c; --warn:#fab219; --warn-bg:#352a10; --mut-bg:#232322;
  --ring:rgba(255,255,255,.10);
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 "Source Sans 3",system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code,.mono,.num{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}
code{font-size:.86em;background:var(--sunk);padding:.08em .32em;border-radius:3px}
.wrap{max-width:76rem;margin:0 auto;padding:0 1.25rem 5rem}
h1,h2,h3{font-family:"Bricolage Grotesque","Helvetica Neue",Arial,sans-serif;text-wrap:balance;margin:0}
h1{font-size:clamp(2rem,4.6vw,2.9rem);font-weight:700;letter-spacing:-.02em;line-height:1.05}
h2{font-size:1.35rem;font-weight:600;letter-spacing:-.01em}
h3{font-size:1rem;font-weight:600}
p{margin:0}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
header{padding:3rem 0 1.5rem;border-bottom:2px solid var(--ink);display:flex;flex-direction:column;gap:1rem}
.lede{font-size:1.05rem;color:var(--ink-2);max-width:62ch}
.meta{display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:var(--muted)}
.meta b{color:var(--ink-2);font-weight:500}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));gap:.75rem;margin:1.5rem 0 0}
.tile{background:var(--surface);border:1px solid var(--rule);padding:.9rem 1rem;display:flex;flex-direction:column;gap:.15rem}
.tile .v{font-family:"Bricolage Grotesque",sans-serif;font-size:1.9rem;font-weight:600;letter-spacing:-.02em;line-height:1.1}
.tile .l{font-size:.78rem;color:var(--muted)}
.tile.warn .v{color:var(--warn)}
section{margin-top:3rem;display:flex;flex-direction:column;gap:1rem}
.sec-head{display:flex;flex-direction:column;gap:.35rem}
.sec-head p{color:var(--ink-2);max-width:70ch}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(21rem,1fr));gap:1rem}
.panel{background:var(--surface);border:1px solid var(--rule);padding:.9rem 1rem 1rem;display:flex;flex-direction:column;gap:.5rem;min-width:0}
.panel-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:.5rem}
.legend{display:flex;flex-wrap:wrap;gap:.35rem .9rem;font-size:.78rem;color:var(--ink-2)}
.legend .key{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:.35rem;border-radius:1px}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--rule);box-shadow:0 2px 10px rgba(0,0,0,.12);padding:.45rem .6rem;font-size:.78rem;min-width:11rem;max-width:18rem;display:none;z-index:2}
.tip .d{font-family:"IBM Plex Mono",monospace;color:var(--muted);font-size:.7rem;margin-bottom:.25rem}
.tip .row{display:grid;grid-template-columns:auto 1fr;gap:.45rem;align-items:baseline}
.tip .row .k{display:inline-block;width:12px;height:2px;border-radius:1px;position:relative;top:-.15em}
.tip .row .val{font-family:"IBM Plex Mono",monospace;font-weight:600;color:var(--ink)}
.tip .row .lab{color:var(--ink-2)}
.tip .row.arm .val{font-weight:400;color:var(--ink-2)}
.note{font-size:.85rem;color:var(--muted)}
.tscroll{overflow-x:auto;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th{font-family:"IBM Plex Mono",monospace;font-size:.66rem;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:left;padding:.55rem .7rem .5rem 0;border-bottom:1px solid var(--rule);white-space:nowrap;position:sticky;top:0;background:var(--surface)}
td{padding:.6rem .7rem .6rem 0;border-bottom:1px solid var(--rule);vertical-align:top;color:var(--ink-2)}
td:first-child,th:first-child{padding-left:.7rem}
tr:last-child td{border-bottom:none}
td.num,th.num{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap;font-size:.8rem}
td.lab{color:var(--ink);font-weight:600}
.delta{font-size:.74rem;margin-left:.3rem}
.delta.up{color:var(--good)}.delta.down{color:var(--crit)}.delta.flat{color:var(--muted)}
.pill{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:.64rem;letter-spacing:.06em;padding:.18rem .45rem;white-space:nowrap;font-weight:500}
.pill.critical{color:var(--crit);background:var(--crit-bg)}
.pill.warning{color:var(--warn);background:var(--warn-bg)}
.pill.muted{color:var(--ink-2);background:var(--mut-bg)}
details{border:1px solid var(--rule);background:var(--surface);padding:.6rem .9rem}
summary{cursor:pointer;font-weight:600;font-size:.9rem}
details .tscroll{border:none;margin-top:.6rem}
footer{margin-top:3.5rem;padding-top:1.2rem;border-top:1px solid var(--rule);font-size:.8rem;color:var(--muted);display:flex;flex-direction:column;gap:.4rem}
@media (prefers-reduced-motion:no-preference){.pt{transition:r .12s ease}}
</style>

<div class="wrap">
<header>
  <p class="eyebrow">cymatix-receipts · ledger.json · every number traces to a receipt</p>
  <h1>Cymatix Receipt Ledger</h1>
  <p class="lede">The measurement trail of Cymatix Context's retrieval work, read straight from the archived receipts: what each bed delivers under shipped defaults, every default that changed and what it bought, and every lever that was measured and did not survive.</p>
  <div class="meta">
    <span>generated <b>{{GEN}}</b></span>
    <span>source <b>Cymatix-Context @ {{SRC}}</b></span>
    <span>window <b>{{DATE_MIN}} → {{DATE_MAX}}</b></span>
    <span>basis <b>delivered_gold_rate</b> unless stated</span>
  </div>
  <div class="tiles">
    <div class="tile"><span class="v">{{N_BEDS}}</span><span class="l">beds measured</span></div>
    <div class="tile"><span class="v">{{N_MEAS}}</span><span class="l">arm × bed × receipt rows</span></div>
    <div class="tile"><span class="v">{{N_GRAD}}</span><span class="l">defaults changed behind a receipt</span></div>
    <div class="tile"><span class="v">{{N_KILLS}}</span><span class="l">levers measured and killed</span></div>
    <div class="tile warn"><span class="v">{{N_MISSING}}</span><span class="l">cited receipts not yet archived</span></div>
  </div>
</header>

<section>
  <div class="sec-head">
    <p class="eyebrow">Delivered gold rate over time</p>
    <h2>What each bed delivers, and what was tried</h2>
    <p>Filled marks are runs of the shipped configuration of their date, joined in order. Hollow marks are every other arm measured on that bed (a knob turned, a lane added, a kill probe). Hover or focus a date for the values; the table view below carries every point.</p>
  </div>
  <div class="panels" id="panels"></div>
  <p class="note">{{N_POINTS}} plotted rows on the delivered basis. {{N_ZERO}} degenerate rows (delivered 0 with recall 0, an empty gold set) were left out. EnronQA v2c is not drawn because its rows are numerically identical to v2 (the hub-cutoff null). Beds with only latency, storage, or map-basis receipts appear in the bed table but not here.</p>
  <details><summary>Table view of the plotted points</summary>
    <div class="tscroll"><table><thead><tr><th>bed</th><th class="num">date</th><th>arm</th><th class="num">delivered</th><th class="num">r@12</th><th class="num">n</th><th>kind</th></tr></thead><tbody>
{{CHART_TABLE}}
    </tbody></table></div>
  </details>
</section>

<section>
  <div class="sec-head">
    <p class="eyebrow">Graduations</p>
    <h2>Defaults that changed, and what the receipt showed</h2>
    <p>A default only moves behind a paired measurement on a pinned bed. Before and after are delivered gold rates on the bed named in the row; the paired column is the per-needle gain and loss when the receipt reports it.</p>
  </div>
  <div class="tscroll"><table><thead><tr><th class="num">date</th><th>change</th><th>bed</th><th class="num">delivered before → after</th><th class="num">paired</th><th>receipt</th></tr></thead><tbody>
{{GRAD_ROWS}}
  </tbody></table></div>
</section>

<section>
  <div class="sec-head">
    <p class="eyebrow">Kill ledger</p>
    <h2>Levers measured and not survived</h2>
    <p>Kills are kept as first-class results so a lever stays dead. Where a receipt states its kill criterion before the run, the ledger quotes it; where only prose survives, the row says so in its receipt column.</p>
  </div>
  <div class="tscroll"><table><thead><tr><th class="num">date</th><th>lever</th><th>bed</th><th>verdict</th><th>deciding result</th><th>receipt</th></tr></thead><tbody>
{{KILL_ROWS}}
  </tbody></table></div>
</section>

<section>
  <div class="sec-head">
    <p class="eyebrow">Beds</p>
    <h2>Every knowledge store that was measured</h2>
    <p>Comparability follows the BASELINES rules: compare arms within a row, and across beds only with matching <code>ingest_c</code> and <code>tagger_version</code>. Latest shipped is the most recent shipped-default delivered rate on that bed.</p>
  </div>
  <div class="tscroll"><table><thead><tr><th>bed</th><th>family</th><th class="num">genes</th><th class="num">tagger</th><th class="num">ingest_c</th><th class="num">latest shipped</th><th class="num">r@12</th><th class="num">date</th><th class="num">rows</th></tr></thead><tbody>
{{BED_ROWS}}
  </tbody></table></div>
</section>

<section>
  <div class="sec-head">
    <p class="eyebrow">Coverage</p>
    <h2>Cited but not yet archived</h2>
    <p>Receipts named in prose or in another receipt's basis list but absent from the archive at the source commit. They are listed rather than filled in; most live on open pull-request branches and land in the mirror when those merge.</p>
  </div>
  <div class="tscroll"><table><thead><tr><th>receipt</th><th>named in</th><th>note</th></tr></thead><tbody>
{{MISSING_ROWS}}
  </tbody></table></div>
</section>

<footer>
  <p>Built by <code>ledger/build_page.py</code> from <code>ledger/ledger.json</code> (<code>ledger/build_ledger.py</code> regenerates the JSON from the mirrored receipts). Repository: <a href="{{REPO_URL}}">cymatix-receipts</a>. Comparability rules: <a href="{{MAIN_URL}}/blob/master/docs/benchmarks/BASELINES.md">BASELINES.md</a>. Three recall-like numbers appear in the receipts and are never merged: <code>recall_at_12</code> (score-map), <code>final_recall_at_12</code> (final order), <code>delivered_gold_rate</code> (delivered slice).</p>
  <p>Source commit {{SRC_FULL}}.</p>
</footer>
</div>

<script>
(function(){
  var DATA = {{DATA_JSON}};
  var SERIES = ["--s1","--s2","--s3"];
  var W = 640, H = 250, ML = 42, MR = 96, MT = 14, MB = 30;
  var days = DATA.dates.map(function(d){ return Date.parse(d + "T00:00:00Z"); });
  var xmin = Math.min.apply(null, days), xmax = Math.max.apply(null, days);
  if (xmax === xmin) { xmax = xmin + 86400000; }
  var pad = (xmax - xmin) * 0.04;
  xmin -= pad; xmax += pad;
  function xs(dstr){ var t = Date.parse(dstr + "T00:00:00Z"); return ML + (t - xmin) / (xmax - xmin) * (W - ML - MR); }
  function ys(v){ return MT + (1 - v) * (H - MT - MB); }
  function el(tag, attrs, ns){ var e = ns ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag); for (var k in attrs) { e.setAttribute(k, attrs[k]); } return e; }
  function cssVar(name){ return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888"; }
  function monthLabel(t){ var d = new Date(t); return ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()] + " " + d.getUTCDate(); }
  var root = document.getElementById("panels");
  DATA.panels.forEach(function(P){
    var panel = el("div", {"class":"panel"});
    var head = el("div", {"class":"panel-head"});
    var h3 = el("h3"); h3.textContent = P.title; head.appendChild(h3);
    var legend = el("div", {"class":"legend"});
    P.beds.forEach(function(b, i){
      var s = el("span"); var k = el("span", {"class":"key"}); k.style.background = "var(" + SERIES[i] + ")";
      s.appendChild(k); s.appendChild(document.createTextNode(P.labels[b])); legend.appendChild(s);
    });
    panel.appendChild(head); panel.appendChild(legend);
    var chart = el("div", {"class":"chart"});
    var svg = el("svg", {"viewBox":"0 0 " + W + " " + H, "role":"img", "aria-label": P.title + ": delivered gold rate over time"}, true);
    // grid + axes
    [0, .25, .5, .75, 1].forEach(function(v){
      svg.appendChild(el("line", {"x1":ML,"x2":W-MR,"y1":ys(v),"y2":ys(v),"stroke":"var(--grid)","stroke-width":1}, true));
      var t = el("text", {"x":ML-6,"y":ys(v)+3,"text-anchor":"end","font-size":"9","font-family":"IBM Plex Mono, monospace","fill":"var(--muted)"}, true);
      t.textContent = v.toFixed(2); svg.appendChild(t);
    });
    svg.appendChild(el("line", {"x1":ML,"x2":W-MR,"y1":ys(0),"y2":ys(0),"stroke":"var(--axis)","stroke-width":1}, true));
    // x ticks: first/last dates + a few in between
    var ticks = DATA.dates.length <= 6 ? DATA.dates : [DATA.dates[0], DATA.dates[Math.floor(DATA.dates.length/3)], DATA.dates[Math.floor(2*DATA.dates.length/3)], DATA.dates[DATA.dates.length-1]];
    ticks.forEach(function(d){
      var t = el("text", {"x":xs(d),"y":H-MB+14,"text-anchor":"middle","font-size":"9","font-family":"IBM Plex Mono, monospace","fill":"var(--muted)"}, true);
      t.textContent = monthLabel(Date.parse(d + "T00:00:00Z")); svg.appendChild(t);
    });
    // series
    P.beds.forEach(function(b, i){
      var col = "var(" + SERIES[i] + ")";
      var shipped = P.points.filter(function(p){ return p.bed === b && p.shipped; }).sort(function(a, c){ return a.date < c.date ? -1 : 1; });
      var arms = P.points.filter(function(p){ return p.bed === b && !p.shipped; });
      // one representative shipped point per date for the step line and the label: the largest n, then the largest value
      var byDate = {};
      shipped.forEach(function(p){ var q = byDate[p.date]; if (!q || (p.n || 0) > (q.n || 0) || ((p.n || 0) === (q.n || 0) && p.d > q.d)) byDate[p.date] = p; });
      var line = Object.keys(byDate).sort().map(function(k){ return byDate[k]; });
      if (line.length > 1) {
        var d = "";
        line.forEach(function(p, j){ var x = xs(p.date), y = ys(p.d); d += (j ? " H" + x + " V" + y : "M" + x + " " + y); });
        svg.appendChild(el("path", {"d":d,"fill":"none","stroke":col,"stroke-width":2,"stroke-linejoin":"round"}, true));
      }
      arms.forEach(function(p){
        svg.appendChild(el("circle", {"class":"pt","cx":xs(p.date),"cy":ys(p.d),"r":3,"fill":"var(--surface)","stroke":col,"stroke-width":1.5,"opacity":".55"}, true));
      });
      shipped.forEach(function(p){
        svg.appendChild(el("circle", {"class":"pt","cx":xs(p.date),"cy":ys(p.d),"r":4.5,"fill":col,"stroke":"var(--surface)","stroke-width":2}, true));
      });
      if (line.length) {
        var last = line[line.length - 1];
        var t = el("text", {"x":xs(last.date)+8,"y":ys(last.d)+3,"font-size":"10","font-family":"IBM Plex Mono, monospace","fill":"var(--ink-2)"}, true);
        t.textContent = P.labels[b] + " " + last.d.toFixed(3); svg.appendChild(t);
      }
    });
    // crosshair + tooltip
    var cross = el("line", {"x1":0,"x2":0,"y1":MT,"y2":H-MB,"stroke":"var(--axis)","stroke-width":1,"stroke-dasharray":"3 3","visibility":"hidden"}, true);
    svg.appendChild(cross);
    var hit = el("rect", {"x":ML,"y":MT,"width":W-ML-MR,"height":H-MT-MB,"fill":"transparent","tabindex":"0"}, true);
    svg.appendChild(hit);
    var tip = el("div", {"class":"tip"});
    var pdates = P.points.map(function(p){ return p.date; }).filter(function(d, i, a){ return a.indexOf(d) === i; }).sort();
    function show(dstr, clientX){
      var pts = P.points.filter(function(p){ return p.date === dstr; }).sort(function(a, c){ return (a.shipped === c.shipped) ? (c.d - a.d) : (a.shipped ? -1 : 1); });
      while (tip.firstChild) tip.removeChild(tip.firstChild);
      var dd = el("div", {"class":"d"}); dd.textContent = dstr; tip.appendChild(dd);
      pts.slice(0, 12).forEach(function(p){
        var row = el("div", {"class":"row" + (p.shipped ? "" : " arm")});
        var k = el("span", {"class":"k"}); k.style.background = "var(" + SERIES[P.beds.indexOf(p.bed)] + ")";
        var v = el("span"); var val = el("span", {"class":"val"}); val.textContent = p.d.toFixed(3);
        var lab = el("span", {"class":"lab"}); lab.textContent = " " + P.labels[p.bed] + (p.shipped ? " · shipped" : " · " + p.arm) + (p.n ? " · n=" + p.n : "");
        v.appendChild(val); v.appendChild(lab); row.appendChild(k); row.appendChild(v); tip.appendChild(row);
      });
      if (pts.length > 12) { var more = el("div", {"class":"d"}); more.textContent = "+" + (pts.length - 12) + " more in the table view"; tip.appendChild(more); }
      cross.setAttribute("x1", xs(dstr)); cross.setAttribute("x2", xs(dstr)); cross.setAttribute("visibility", "visible");
      tip.style.display = "block";
      var rect = chart.getBoundingClientRect();
      var left = (clientX != null) ? (clientX - rect.left + 14) : (xs(dstr) / W * rect.width + 14);
      if (left + 220 > rect.width) left = Math.max(0, left - 240);
      tip.style.left = left + "px"; tip.style.top = "12px";
    }
    function hide(){ tip.style.display = "none"; cross.setAttribute("visibility", "hidden"); }
    var idx = 0;
    hit.addEventListener("pointermove", function(ev){
      var rect = svg.getBoundingClientRect(); var x = (ev.clientX - rect.left) / rect.width * W;
      var best = null, bd = 1e9;
      pdates.forEach(function(d, i){ var dx = Math.abs(xs(d) - x); if (dx < bd) { bd = dx; best = d; idx = i; } });
      if (best) show(best, ev.clientX);
    });
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", function(){ if (pdates.length) show(pdates[idx]); });
    hit.addEventListener("blur", hide);
    hit.addEventListener("keydown", function(ev){
      if (ev.key === "ArrowRight") { idx = Math.min(pdates.length - 1, idx + 1); show(pdates[idx]); ev.preventDefault(); }
      if (ev.key === "ArrowLeft") { idx = Math.max(0, idx - 1); show(pdates[idx]); ev.preventDefault(); }
    });
    chart.appendChild(svg); chart.appendChild(tip); panel.appendChild(chart); root.appendChild(panel);
  });
})();
</script>
"""

if __name__ == "__main__":
    main()
