# MemoFlow 更新配置说明

本目录包含应用使用的更新配置 JSON。

文件：`memoflow_update.json`

## 顶层字段

- `version_info`
  - `latest_version`：最新版本号，用于更新提示与对比。
  - `is_force`：是否强制更新，强制时只能退出。
  - `download_url`：更新按钮跳转的下载地址。
  - `debug_version`：调试构建使用的版本号（有值时优先）。
- `debug_announcement_source`
  - 控制调试构建使用哪一种公告内容。
  - 取值：`debug` / `debug_announcement` / `announcement` 使用 `debug_announcement`。
  - 取值：`release` / `release_notes` / `release_announcement` 使用 release notes。
  - 仅在 debug 构建生效。
- `debug_announcement`
  - 调试公告内容，仅在 `debug_announcement_source` 选择 debug 时使用。
  - 结构与 `announcement` 相同。
- `announcement`
  - `id`：公告 ID（整数）。
  - `title`：弹窗标题。
  - `contents`：按语言分组的字符串列表（如 `zh` / `en`）。
  - `new_donor_ids`：本次特别鸣谢的 donor ID 列表（可选）。
- `release_notes`
  - 版本更新日志数组，每条包含：
    - `version`：版本号（如 `1.0.6`）。
    - `date`：日期展示字符串。
    - `items`：分组数组，每组包含：
      - `category`：类别文本（映射为 新增/优化/修复）。
      - `contents`：该类别下的多行内容。
- `donors`
  - 赞助者列表，每个包含 `id` / `name` / `avatar`。

## 行为说明（应用侧）

- Debug 构建：
  - 若 `debug_version` 有值，则使用它作为当前版本号。
  - 若 `debug_announcement_source` 指向 debug，则弹窗展示 `debug_announcement.contents`。
  - 否则按当前版本号匹配 release notes 展示。
- Release 构建：
  - 始终使用 release notes 展示。
- 当 `latest_version` 大于当前版本时，弹窗会出现“更新”按钮。
- 公告已读后不会重复弹出，除非版本变化或清除本地存储。

## 常用提示

- 想重新弹出 debug 公告，可直接修改 `debug_version`。
- 应用实际读取的是更新配置 URL；若要用本地 JSON，需要把 URL 指向本地服务或文件路径。
