# Tasks: guided-release-config-manager

## 1. 数据面板设计与后端只读数据

- [x] 1.1 Define normalized GitHub release/asset DTOs for dashboard use.
- [x] 1.2 Add server-side GitHub token loading from `MEMOFLOW_CONFIG_GITHUB_TOKEN` and repo override from `MEMOFLOW_CONFIG_GITHUB_REPO`.
- [x] 1.3 Add a token-free cache strategy and clear rate-limit/error states for GitHub release fetches.
- [x] 1.4 Add dashboard aggregation that combines GitHub releases with local `manifest`, announcements, translations, and update candidates.

## 2. 步骤式本地发布向导

- [x] 2.1 Define release draft shape covering announcement, donor changes, update candidates, localization, and build option.
- [x] 2.2 Implement draft preview data without writing source files before final publish.
- [x] 2.3 Add dry-run validation against a temporary `update/` tree before publish.
- [x] 2.4 Publish local files only and explicitly avoid `git commit`, `git push`, gh-pages publish, GitHub Actions dispatch, and Cloudflare Worker calls.
- [x] 2.5 Run post-save validation and optionally build `dist/update/latest.json`.

## 3. 按版本分组管理

- [x] 3.1 Add version grouping across GitHub releases, source announcements, localized announcements, update candidates, and legacy `version_info`.
- [x] 3.2 Use semver-like descending sort for grouped versions.
- [x] 3.3 Allow management actions from a version group: edit source announcement, edit localizations, edit update candidates, set latest, delete with safeguards.
- [x] 3.4 Surface status summaries such as missing translations, stale translations, missing download links, and local/GitHub version mismatch.

## 4. UI 重组

- [x] 4.1 Make dashboard the default landing view.
- [x] 4.2 Replace scattered release creation flows with the six-step release wizard.
- [x] 4.3 Move existing announcement/localization/update/donor edit affordances into grouped management or wizard steps where appropriate.
- [x] 4.4 Keep validation/build command output discoverable from the release flow and diagnostics area.

## 5. 验证

- [x] 5.1 Add or update `config` unittest coverage for GitHub data normalization, version grouping, draft dry-run validation, and local-only publish boundaries.
- [x] 5.2 Run `python -m unittest discover -s config -p "test_*.py"`.
- [x] 5.3 Run `python .github/scripts/build_update_config.py --root update --validate-only` after any saved `update/` fixture or source changes.

## 6. 反馈修正

- [x] 6.1 Release wizard announcement content MUST use the existing grouped announcement format with fixed categories: feature, improvement, and fix.
- [x] 6.2 Release wizard SHOULD support AI summary generation from the grouped update content.
- [x] 6.3 Release wizard donor step MUST allow adding/editing donor id, name, and avatar upload before publishing.
- [x] 6.4 Release wizard localization targets MUST use multi-select choices instead of free-form locale input.
- [x] 6.5 Release wizard download links MUST come from editable update candidate rows rather than reduced platform URL fields.
- [x] 6.6 Release wizard fixed announcement categories MUST use one textarea per category and parse each non-empty line as one update item.
- [x] 6.7 Release wizard draft preview SHOULD match the existing announcement preview format instead of showing only counts.
- [x] 6.8 Release wizard SHOULD present update candidate rows as current-version download links in user-facing copy.
- [x] 6.9 Release wizard download links SHOULD render platform logo cards with gray/green completion indicators and edit details in a centered modal.
- [x] 6.10 Release wizard download modal SHOULD be larger and use platform logo choices instead of a text platform selector.
- [x] 6.11 Release wizard download modal MUST override the default modal width and platform cards MUST show icons instead of text labels.
- [x] 6.12 Release wizard MUST only publish completed download links and MUST NOT overwrite existing updates when all platform cards are empty.
