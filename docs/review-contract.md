# 人工复核契约（任务16）

迁移 `160_reviews.sql`，模块 `aqp.reviews`，候选结果页面内 `ReviewPanel`。复核是辅助候选建议，不生成正式优秀评审。

- `GET /api/candidate-results/{candidate_id}/reviews` 为任务18提供只读复核与版本依据，返回 candidate_id、version、stale、items。每次经候选读取边界重查目标和全部历史证据的当前 view/analyze/identity 授权，身份授权不足拒绝整个读取，避免自由文本意见泄露身份或原文。无需 review 写权限即可按上述范围只读。
- `POST` 同路径，独立要求目标全部关联学生的 papers.review 授权，管理员角色不替代授权。decision 仅建议推荐／不建议推荐／待补充材料，comment 必填。expected_version 从0开始；冲突409。request_id 16–64字，同一操作者同内容重试返回原记录，不同内容或候选复用409；重试仍重查当前权限。
- 本人 mode=self（默认）从登录账号确定 confirmed_by；代录 mode=proxy 必填 confirmed_by、basis，recorded_by 独立保存实际操作账号ID。created_at 是服务器实际录入时间；代录不伪造专家亲自登录或历史签字时间。
- 每条意见追加 version，保存完整候选 evidence 快照，绑定候选ID、比较分析快照 comparison_id、解析分析/论文版本 paper_version_id、file_sha256、规则ID/版本以及各样本 evidence_versions。当前架构解析分析随 paper_version_id 固定，不存在独立模型分析版本。无更新/删除 API；旧意见不覆盖。
- 过时候选禁止新写入409，历史仍可在当前授权内读取；每次读取重新计算外层 stale。仅该候选最新意见且候选未过时时 current_confirmation=true，此字段不代表正式评审确认。evidence 是历史快照，其内部 stale 是写入时状态，消费方必须使用外层 stale/current_confirmation。
- 审计只记录动作、对象ID与操作者，不存意见、专家姓名、书面来源或正文。

验证：65项完整 pytest、mypy、Ruff、TS/Vite 构建通过；Chrome8046临时合成数据完整创建规则/候选、复核首版及修订、查看两版意见。`uv run python backend/tests/browser_reviews.py` 可复现，finally 恢复并核验原授权、停止服务器、清理临时库。浏览器脚本使用锁定 Playwright 与本机 Chrome。
