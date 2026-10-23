# claude/jev-packet-assembly-test-138065

branch: `claude/jev-packet-assembly-test-138065`
head: `49cd5859ea64664546558ebfbfe7b63a213f4fc1` (refs/heads/claude/jev-packet-assembly-test-138065)
diff base: `a2793a7a75ba6650614be20b91ced221cca68427` (merge-base with parent branch `bench/c580-multicorpus`)
pr: local only, no PR
exported: 2026-10-23T16:11:51.794192+00:00
files: 7
bytes: 9857172 (largest 4383724: `benchmarks/dogfood/jev/jev_erb_packet_know_c4000_classcap_2026-10-23.json`)

## Reading note: EXPERIMENTAL external model

Local-only branch (never pushed), cut from `bench/c580-multicorpus` for its c4000 classcap
profile; the diff base is that branch, so only the Jev files are here. Jev (TypeSafe
"System One", jev-1.14.0) is a proprietary hosted API, not part of the cymatix pipeline.
Receipts: 239b synthetic bed (know/miss 72/72), ERB 947k c4000 classcap with cymatix
incoming rankings (packet AUROC 0.906; delivery identical to the 10-19 ladder 470/470),
and the paired no-incoming ablation (0.900, delta CI [-0.015, +0.004]). Each receipt
carries every raw Jev response, so `--rescore` needs no key. Write-up:
`docs/benchmarks/2026-10-23-jev-system-one-packet-judge.md` on the System One PR.

- benchmarks/dogfood/jev/compare_jev_arms.py
- benchmarks/dogfood/jev/compare_with_vs_no_incoming_erb_c4000_2026-10-23.json
- benchmarks/dogfood/jev/jev_239b_packet_know.py
- benchmarks/dogfood/jev/jev_239b_packet_know_grain_c4000_classcap_2026-10-23.json
- benchmarks/dogfood/jev/jev_erb_packet_know.py
- benchmarks/dogfood/jev/jev_erb_packet_know_c4000_classcap_2026-10-23.json
- benchmarks/dogfood/jev/jev_erb_packet_know_c4000_classcap_noincoming_2026-10-23.json
