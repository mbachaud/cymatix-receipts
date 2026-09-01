# beds/

Archived knowledge-store snapshots (benchmark "beds") are too large for git, so
they are published as **GitHub Release assets** on this repository rather than
committed here. Each asset is a zstd-compressed SQLite store named `<bed>.db.zst`.

This directory holds only the manifest that describes them:

- `MANIFEST.json` (not yet present) records one entry per published asset with
  its release tag, asset filename, uncompressed and compressed byte counts, and
  the sha256 of the uploaded `.db.zst`.

The manifest arrives with the first release. A sibling agent uploads the bed
assets and writes `beds/MANIFEST.json` at that time. Until then this directory
is intentionally empty of data.

## Verifying a downloaded bed

```bash
# after downloading <bed>.db.zst from the release page
sha256sum <bed>.db.zst          # compare against the entry in MANIFEST.json
zstd -d <bed>.db.zst -o <bed>.db
```

Bed identity for benchmark purposes is not the file sha256. It is the
content-derived gene identity plus the `ingest_c` and `tagger_version` recorded
for that bed in the main repository's baselines ledger. See the citation rules
in the top-level `README.md`.
