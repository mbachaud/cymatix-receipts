# claude/jev-packet-assembly-test-138065

branch: `claude/jev-packet-assembly-test-138065`
head: `f1a23ae33c68f81aad840c8638432fe14a74e793` (refs/heads/claude/jev-packet-assembly-test-138065)
diff base: `a2793a7a75ba6650614be20b91ced221cca68427` (merge-base with parent branch `bench/c580-multicorpus`)
pr: local only, no PR
exported: 2026-10-23T19:38:42.477766+00:00
files: 16
bytes: 29572520 (largest 7407676: `benchmarks/dogfood/jev/laya_erb_packet_know_c4000_classcap_typeddecisions1024_2026-10-23.json`)

## Reading note: EXPERIMENTAL external model

Local-only branch (never pushed), cut from `bench/c580-multicorpus` for its c4000 classcap
profile; the diff base is that branch, so only the Jev files are here. Jev (TypeSafe
"System One", jev-1.14.0) is a proprietary hosted API, not part of the cymatix pipeline.
Receipts: 239b synthetic bed (know/miss 72/72), ERB 947k c4000 classcap with cymatix
incoming rankings (packet AUROC 0.906; delivery identical to the 10-19 ladder 470/470),
and the paired no-incoming ablation (0.900, delta CI [-0.015, +0.004]). Each receipt
carries every raw Jev response, so `--rescore` needs no key. Write-up:
`docs/benchmarks/2026-10-23-jev-system-one-packet-judge.md` on the System One PR (#522).

Local comparison (`laya_*.json`): Laya 0.4.14 (ConvAI Innovations, Apache-2.0) served by
laya-serve on an RTX 3080 Ti, checkpoints english@512 / multilingual@8192 /
typed-decisions@1024 (revision 7b928d82), same no-incoming questions and the same 470 ERB
packets as the Jev arm. ERB packet AUROC 0.563 (multilingual) / 0.480 (typed-decisions) vs
Jev 0.900; `laya_truncation_2026-10-23.txt` gives Laya's own truncation counts (typed-decisions
read p50 944 of 9,057 packet tokens).

- benchmarks/dogfood/jev/compare_jev_arms.py
- benchmarks/dogfood/jev/compare_jev_vs_laya_erb_c4000_2026-10-23.json
- benchmarks/dogfood/jev/compare_jev_vs_laya_typeddecisions_erb_c4000_2026-10-23.json
- benchmarks/dogfood/jev/compare_with_vs_no_incoming_erb_c4000_2026-10-23.json
- benchmarks/dogfood/jev/jev_239b_packet_know.py
- benchmarks/dogfood/jev/jev_239b_packet_know_grain_c4000_classcap_2026-10-23.json
- benchmarks/dogfood/jev/jev_erb_packet_know.py
- benchmarks/dogfood/jev/jev_erb_packet_know_c4000_classcap_2026-10-23.json
- benchmarks/dogfood/jev/jev_erb_packet_know_c4000_classcap_noincoming_2026-10-23.json
- benchmarks/dogfood/jev/laya_239b_packet_know_grain_c4000_classcap_english512_2026-10-23.json
- benchmarks/dogfood/jev/laya_239b_packet_know_grain_c4000_classcap_multilingual8192_2026-10-23.json
- benchmarks/dogfood/jev/laya_239b_packet_know_grain_c4000_classcap_typeddecisions1024_2026-10-23.json
- benchmarks/dogfood/jev/laya_erb_packet_know_c4000_classcap_multilingual8192_2026-10-23.json
- benchmarks/dogfood/jev/laya_erb_packet_know_c4000_classcap_typeddecisions1024_2026-10-23.json
- benchmarks/dogfood/jev/laya_truncation.py
- benchmarks/dogfood/jev/laya_truncation_2026-10-23.txt
