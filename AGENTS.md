# AGENTS.md

## 项目定位
- 本仓库是 `MemoFlow` 的独立配置仓库，主要维护更新元数据、公告内容、捐赠者列表和发布产物，不是主应用代码仓库。
- 以 `update/` 目录为配置源；`dist/update/` 为构建输出；`cloudflare/update-config-worker/` 为自动化更新 Worker。

## 目录约定
- `update/manifest.json`：全局更新配置、平台版本信息、公告索引。
- `update/announcements/*.json`：每个公告一个文件。
- `update/donors.json`：捐赠者数据。
- `update/assets/*`：静态资源文件。
- `memoflow_update.json`：兼容旧客户端的镜像配置。
- `dist/update/*.json`：构建或发布产物，除非任务明确要求，否则不要把这里当作唯一事实来源。

## 修改原则
- 优先做最小范围修改，不改无关字段，不随意重排结构。
- 涉及公告新增或版本发布时，保持 `update/manifest.json` 中以下字段同步：
  - `announcement_tag_index`
  - `announcement_ids`
  - `latest_announcement_id`
- `items[].category` 应保持稳定，默认使用 `feature`、`improvement`、`fix`，不要随意改成展示文案。
- 修改配置前，先参考 `README.md`、`update/README.md` 与现有 JSON 结构，避免臆造字段。

## JSON 与编码要求
- 所有 `.json` 文件必须保存为 `UTF-8`（无 BOM）。
- 修改 JSON 时必须保留合法格式，不能破坏中文内容、数组顺序和现有字段语义。
- 若批量处理编码，先确认不会把 UTF-8 中文误转成乱码。

## 校验与构建
- 修改 `update/` 下配置后，优先运行：
  - `python .github/scripts/build_update_config.py --root update --validate-only`
- 需要生成预览产物时，运行：
  - `python .github/scripts/build_update_config.py --root update --output dist/update/latest.json`

## 协作说明
- 若任务涉及 Cloudflare Worker 或发布流程，检查 `cloudflare/update-config-worker/README.md` 与 `.github/workflows/` 中的约定后再修改。
- 如需求不明确，先基于仓库内文档与现有样例确认，再继续编辑；不要编造接口、字段或发布规则。
