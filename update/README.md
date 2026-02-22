# Update Config Layout

This folder stores MemoFlow update configuration as split files in the standalone `memoflow_config` repository.

## Files

- `manifest.json`: global settings and index pointers.
- `donors.json`: donor list consumed by client UI.
- `announcements/{id}.json`: one announcement per file.
- `assets/*`: static donor avatar assets published to `update/assets/`.

## Workflow

1. Update `donors.json`, `announcements/*.json`, and `manifest.json`.
2. Open a PR and let `Update Config Validate` check references.
3. Push a `v*` tag and build release assets (optional).
4. `Update Config Build` generates merged `latest.json`.
5. `Update Config Publish` publishes:
   - `update/latest.json`
   - `update/versions/latest-*.json`
   - `update/index.json`
   - `update/assets/*`

## Announcement File Fields

- `id`: unique numeric string, should never be reused.
- `release_tag`: optional idempotency marker, e.g. `v1.0.15`.
- `version`: display version for release notes.
- `date`: display date label.
- `title`: dialog title.
- `show_when_up_to_date`: whether to show dialog when no update exists.
- `contents`: localized summary paragraphs.
- `new_donor_ids`: optional donor IDs to highlight.
- `items`: grouped release note details.
  - `category`: stable key, recommend `feature|improvement|fix`.
  - `contents`: localized object, e.g. `{ "zh": [...], "en": [...] }`.
