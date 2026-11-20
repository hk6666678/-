# 候选规则与结果契约（任务15）

迁移 `150_candidates.sql`。默认无规则；没有任何自动启用的业务标准。独立模块 `aqp.candidates` / `CandidatePanel`。

- `POST /api/candidate-rules` 新建不可覆盖的草稿，必填 name、college、major、level、conditions、required_evidence（目前仅 pages）、minimum_samples（优秀/普通每项有效分母最少1）、missing_policy（仅 insufficient）；synthetic 标明合成软件验证。previous_id 可派生同规则家族的新版本。范围为一个学院+专业+培养层次，不自动跨学科。特征只支持四项任务14本地计数，运算符仅 gte/lte/eq，数值有限且非负，拒绝额外字段和任意代码/SQL。
- `GET /api/candidate-rules` 只读取当前 candidate_rules 授权范围历史；维护、确认启用均检查 papers/candidate_rules，管理员角色不代替授权。
- `POST /api/candidate-rules/{id}/enable` 接收 confirmed_by、basis，记录业务专家确认来源，实际创建操作人独立保存。一经确认不可原地覆盖、不可重复启用；新确认版本替换同家族旧启用版本，旧配置与确认记录保留。
- `POST /api/candidate-results` 接收 comparison_id。沿用任务14最新样本快照/evidence_versions 校验，过时比较409；创建稳定且不可覆盖的结果ID。无规则、必要原页缺失、特征缺失或对照有效样本不足均不得肯定推荐。逐条件返回 命中/未命中/证据不足；同规则全部命中才推荐，不同启用规则为或关系。
- `GET /api/candidate-results/{id}` 每次重查目标和全部历史证据当前 view+analyze+identity，范围撤销403，绝不借历史快照读取越权结果；重新检查比较证据与当前适用规则ID集合，规则启用或证据变化则 stale=true。草稿不生效，不使当前结果过时。历史推荐值保留为快照，消费方必须先检查 stale，过时结果不可作为当前推荐。

任务16请绑定候选 `id`、paper_version_id、file_sha256、comparison_id、各项 rule_id/rule_version，及 evidence_versions（含样本文件hash、标签版本）。先通过上述GET重查权限与stale，再创建人工复核。结果含 rules（完整已确认规则快照、checks、missing）、groups、evidence_url。原页证据仍通过任务11接口单独检查授权；下载需要download。所有新操作写审计，授权拒绝脱敏。

候选仅辅助推荐供专家复核，不是正式优秀评审结果或概率。没有调用模型。合成规则不构成真实专家标准效果验证；真实规则效果留任务23验收。

软件验证：公开API覆盖草稿/启用/新版本、无规则、三态、样本不足、缺原页、旧比较拒绝、权限撤销、未知可执行条件拒绝；Chrome 8045独立临时合成数据库读取候选1、命中、对照组和页1原文。窗口截图超时，AX树和HTTP请求证实页面结果。测试授权在finally恢复并核验。

可复现浏览器验收：`npm --prefix frontend run build` 后运行 `uv run python backend/tests/browser_candidates.py`（需本机Chrome；端口默认8045，可设AQP_TEST_PORT）。脚本在临时库通过页面完整创建合成草稿、确认启用、生成比较、生成命中候选、查看原页与重读历史；finally恢复授权并关闭服务器，临时数据随后清理。Playwright作为锁定开发依赖；真实专家业务标准没有默认激活。
