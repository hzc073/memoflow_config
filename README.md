# MemoFlow Config Repository

This repository is now the standalone source of truth for MemoFlow update metadata.

## Structure

- `update/manifest.json`: global update settings and announcement indexes.
- `update/donors.json`: donor list.
- `update/announcements/*.json`: one announcement per file.
- `update/assets/*`: donor avatar assets.
- `memoflow_update.json`: compatibility mirror for legacy clients.

## Publish Output

The CI workflows build and publish:

- `update/latest.json`
- `update/versions/latest-*.json`
- `update/index.json`
- `update/assets/*`

## Notes

- Announcement details use multilingual structure in `items[].contents`, for example:
  - `"contents": { "zh": [...], "en": [...] }`
- Keep `category` stable (`feature`, `improvement`, `fix`) so clients can localize labels.
- Cloudflare Worker source is in `cloudflare/update-config-worker/`.
