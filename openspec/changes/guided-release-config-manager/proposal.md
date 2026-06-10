# Change Proposal: guided-release-config-manager

## Why

现有 `config/` 本地配置管理器以分散的 CRUD 面板为主，适合逐项编辑 `update/manifest.json`、公告、翻译、捐赠者和更新候选，但不适合作为一次版本发布的操作入口。发布时操作者需要在多个面板之间切换，手动理解 GitHub release assets、本地 `version_info`、`updates[]`、公告索引、本地化文件和构建结果之间的关系。

本变更将本地配置管理器重新组织为“发布控制台”：

- 默认打开 GitHub 数据面板，查看 release 发布时间、asset 下载数、版本下载量对比和本地配置同步状态。
- 使用步骤式向导完成一次更新版本发布。
- 在管理中心按版本号聚合主公告、本地化公告、更新候选、GitHub release 和捐赠者引用，避免平铺所有公告文件和语言文件。

## What Changes

- 新增 `release-dashboard` 能力，用服务器端只读 GitHub release 数据驱动默认数据面板。
- 新增 `guided-release-publishing` 能力，把添加更新版本组织为 draft-first 的步骤式本地发布流程。
- 新增 `version-grouped-management` 能力，按 version/tag 聚合管理公告、翻译、下载链接和发布状态。
- GitHub token 仅从本地环境变量读取，不进入浏览器端、不写入公开配置。
- 发布仅写本地配置文件，可选构建 `dist/update/latest.json`；不自动 commit、push、发布 gh-pages 或触发 GitHub Actions。

## Non-goals

- 不实现自动 `git commit`、`git push`、GitHub Actions dispatch 或 gh-pages 发布。
- 不把 GitHub token 暴露给浏览器端。
- 不把 `dist/update/*` 改为主要事实源。
- 不改变现有 `update/` JSON schema 的客户端语义，除非后续 spec 明确要求。
- 不删除现有 Cloudflare Worker 自动化；本变更只要求新 UI 与现有 `announcement_tag_index` 幂等规则兼容。

## Impact

- 主要影响文件预计为 `config/server.py`、`config/manager.html`、`config/manager.css`、`config/manager.js`。
- 可能新增本地-only GitHub 配置/缓存读写位置，但 token MUST 来自环境变量，例如 `MEMOFLOW_CONFIG_GITHUB_TOKEN`。
- 继续写入现有事实源：`update/manifest.json`、`update/announcements/*.json`、`update/locales/{locale}/announcements/*.json`、`update/donors.json`、`update/assets/*`。
- 需要覆盖本地配置管理器测试，并在变更后运行 `python -m unittest discover -s config -p "test_*.py"`。
- 涉及 `update/` 的发布保存路径后，必须运行 `python .github/scripts/build_update_config.py --root update --validate-only`。
