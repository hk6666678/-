# 论文标签和比较契约（任务14）

`GET /api/papers/{version_id}/labels` 返回待评默认值、当前标签版本与不可覆盖历史；`POST` 同路径接收 `label`（优秀/普通/待评）、`confirmed_by`、`basis`、`expected_version`，实际录入人取登录账号。写入独立要求 papers/labels 与全体涉及学生 identity 权；历史要求 view+identity；并发版本冲突409。标签绑定文件版本，换文件不会继承优秀标签。

`POST /api/papers/{version_id}/comparisons` 接收 `{year:""}`（空表示全部年度），生成不可覆盖的比较ID。`GET /api/paper-comparisons/{id}` 重查全体证据当前查看及分析范围，再返回历史结果及 `stale`。新文件、标签、基础特征、可用样本集变化均检测为过时；不改写原结果。

返回 target_version_id、target_features、level、discipline、year、groups（优秀/普通/待评）、evidence_versions、notice、sufficient。每组有 sample_count，每项有 missing、denominator、mean；缺失不计0，未标注不计普通，排除目标学生的全部版本，仅使用每位学生最新版本，同层次同学科匹配，不自动跨学科。范围仅为当前用户授权的样本。缺必要组或有效分母时 sufficient=false，任何计数差异都不构成优秀结论或自动候选判定。

任务15可使用比较ID和 evidence_versions 中的 version_id、sha256、label_version 与特征快照绑定规则结果；消费时必须先重新读取比较并拒绝 stale。证据页正文与原件仍走任务11下载/身份授权边界。feature_values 是通用特征适配入口；语义模块未就绪不阻塞基础计数比较。只返回计数，不返回正文、姓名、学号、文件名或标题。所有操作有审计，拒绝授权审计脱敏。合成验证不构成真实专家标准验收。
