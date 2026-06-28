# Change Proposal: optimize-config-webpage

## Why

`config/` 本地配置管理网页在实际使用中暴露出布局沉重、入口过多、文案偏专业、发布向导缺少中途保存、AI 翻译反馈不足，以及首页最新版本排序不清晰等问题。

## What Changes

- 将侧边栏精简为 4 个主入口：`数据面板`、`版本发布`、`内容维护`、`系统设置`。
- 数据面板取消右侧配置状态区域，并按 semver-like 最新版本优先展示下载量。
- 版本发布向导改为单栏流程，增加 `保存草稿`，将预览集中到第 5 步。
- 将 AI 翻译入口并入版本发布向导，同时保留内容维护中的翻译审核能力。
- 内容维护和系统设置通过内部标签页承载原有低频功能，减少侧边栏按钮。
- 将“校验/构建”等专业文案改为“检查配置/生成客户端文件”等更直观表述。
- 使用 Pencil 产出设计图和实际页面截图，保存在本 change 目录。

## Non-goals

- 当前阶段不改变 `update/` JSON schema、发布规则或 Cloudflare Worker 行为。
- 当前阶段不写入 `dist/update/*` 生成产物。
- 不自动执行 `git commit`、`git push`、GitHub Actions 或 Cloudflare Worker 发布。

## Impact

- 影响文件为 `config/manager.html`、`config/manager.css`、`config/manager.js`。
- 不修改 `update/` 配置事实源，不修改 `dist/update/*` 生成产物。
- 需要运行 `python -m unittest discover -s config -p "test_*.py"` 验证本地配置管理器既有逻辑。
