# Design: guided-release-config-manager

## Overview

目标不是重绘现有页面，而是重塑操作者模型：

```text
打开工具
  │
  ▼
GitHub / Local Config Dashboard
  │
  ├─ 添加更新版本 -> 步骤式发布向导
  │
  └─ 管理 -> 按 version/tag 分组管理
```

后端仍由 `config/server.py` 作为 localhost service boundary 负责文件系统访问。浏览器端只调用本地 API，不直接读写仓库文件，也不直接持有 GitHub token。

## Architecture

```text
Browser UI
  │
  ├─ GET /api/dashboard
  │     shows GitHub releases + local config health
  │
  ├─ GET /api/release-groups
  │     groups local announcements/locales/updates with GitHub releases
  │
  └─ POST /api/release-draft/*
        validates and publishes a local-only release draft

config/server.py
  │
  ├─ GitHubReleaseService
  │     token: MEMOFLOW_CONFIG_GITHUB_TOKEN
  │     repo:  MEMOFLOW_CONFIG_GITHUB_REPO or hzc073/memoflow
  │     cache: local, token-free, short TTL
  │
  ├─ ConfigRepository
  │     reads/writes update/ source files
  │
  └─ Build/Validate Runner
        existing .github/scripts/build_update_config.py
```

## GitHub Data

GitHub release data is read-only. The local service should fetch releases and assets from the app repo, then expose normalized dashboard data to the browser.

Important constraints:

- `download_count` is cumulative per release asset. It supports current comparison, not historical trend charts.
- Trend charts require local snapshots over time. That is optional future work unless explicitly scoped.
- Unauthenticated GitHub API is too limited for reliable dashboard use. The service should support `MEMOFLOW_CONFIG_GITHUB_TOKEN` and show a clear unauthenticated/rate-limited state.
- Cached GitHub data must not include or expose the token.

## Release Draft Flow

The release wizard should maintain a draft until final publish.

```text
Step 1: 新建版本更新公告
  - select GitHub release/tag or enter version manually
  - edit title/date/summary/items
  - map release_tag and version

Step 2: 选择是否添加捐赠者
  - select existing donors
  - optionally add donor records/assets

Step 3: 选择是否更新下载链接
  - map GitHub assets to platforms/channels
  - update v3 updates[]
  - optionally sync selected candidates to legacy version_info

Step 4: 是否翻译成多语言版本
  - choose target locales
  - generate or skip localized files
  - show review/stale status

Step 5: 预览和检查
  - preview source announcement, localized outputs, update candidates, donors
  - show file-level write plan
  - run dry-run validation against a temporary update tree

Step 6: 发布
  - write local files only
  - run validation after save
  - optionally build dist/update/latest.json
```

## Dry-run Validation

Step 5 should validate the draft before writing source files. Since the existing build script reads from `update/`, the service can create a temporary copy of the relevant source tree, apply the draft overlay, then run:

```text
python .github/scripts/build_update_config.py --root <temp-update> --validate-only
```

This keeps preview/check meaningful and avoids validating only the old saved state.

## Version Grouping

The management view should group related records by normalized version:

```text
VersionGroup
  version
  release_tags[]
  github_release?
  source_announcements[]
  localized_announcements_by_locale
  update_candidates[]
  legacy_version_info_platforms[]
  donor_references[]
  status_summary
```

Grouping key priority:

```text
release_tag without leading "v"
  -> announcement.version
  -> update.version
  -> GitHub release tag without leading "v"
```

Sorting should be semver-like descending, not plain string sorting.

## Local-only Publish Boundary

Publish means local repository mutation only:

- MAY write `update/manifest.json`
- MAY write `update/announcements/*.json`
- MAY write `update/locales/{locale}/announcements/*.json`
- MAY write `update/donors.json`
- MAY write `update/assets/*`
- MAY build `dist/update/latest.json` when selected

Publish MUST NOT:

- run `git commit`
- run `git push`
- publish `gh-pages`
- trigger GitHub Actions
- call Cloudflare Worker update endpoints

## Open Questions

- Should Step 6 build `dist/update/latest.json` default to enabled or disabled?
- Should dashboard cache snapshots be retained for trend charts in a later change, or should this change only show current cumulative GitHub counts?
- Should GitHub release body be parsed into announcement items, or should Git commit range generation remain the primary source for item details?
