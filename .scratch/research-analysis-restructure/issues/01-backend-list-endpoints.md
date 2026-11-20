# 01 后端只读列表端点

Status: resolved

新增两个 GET 列表端点，支撑前端下拉选择替代手输数字 ID：

- `GET /api/paper-comparisons`（backend/aqp/comparisons.py，仿 evaluation.py snapshot_listing 模式）：复用 comparison() 的授权逻辑（目标论文 covered 学生 papers view+analyze，无权条目跳过），返回 `{items:[{id, created_at, target_version_id, level, discipline, year, stale}]}`，id 倒序。
- `GET /api/candidate-results`（backend/aqp/candidates.py）：复用结果读取授权（papers view+analyze+identity），返回 `{items:[{id, comparison_id, recommended, stale}]}`，id 倒序。

各加 pytest 用例：授权过滤（无权不可见）、字段形状、空库。不改任何现有端点与权限逻辑。

## Answer

已实现：comparisons.py 新增 `GET /api/paper-comparisons`（复用 paper() 授权，无权跳过；stale 仅快速检测目标版本替换，成员漂移由详情接口复核，代码注释说明）；candidates.py 新增 `GET /api/candidate-results`（复用 comparison() 的 view+analyze+identity 授权，顺带取完整 stale）。各加 1 项 pytest（字段形状、stale 变化、撤权隐藏），2 项通过 2.60 秒。未改现有端点。

## Comments
