# 分析与证据 API 契约（课程 v1）

任务 09、17、19 的只读消费者可使用此契约；认证、CSRF 与统一授权沿用现有 API。业务管理员身份不提供隐含数据权限。

- `POST /api/analyses/courses`：`college` 必填、`major` 可留空；留空表示当前账号在该学院同时具备 view 与 analyze 的专业集合，学院级授权表示全部专业。`course_code`、`term` 可选，空表示范围内全部。每次生成新快照，返回独立 `id`，不覆盖历史。
- `GET /api/analyses`：仅返回当前仍有权读取的历史快照。
- `GET /api/analyses/{id}` 和 `/{id}/evidence`：返回 `category`、`scope`、`created_at`（Unix 秒）、`data_version`、`rule_version`、`stale`、`result`、`evidence`。两条读取路径内容相同。
- `GET /api/analyses/{id}/export`：同一快照的 JSON 导出边界，额外检查 export；供任务 19 的 Excel 导出消费。证据按当前 identity 授权脱敏，原快照保持不变。
- `GET /api/pass-rules?college=...&major=...`：规则历史；`POST /api/pass-rules`：业务确认后追加版本，独立检查 courses/pass_rules。规则包含学院、专业、课程、评分制度、可选学期、确认依据、操作人和时间。百分制填 threshold；等级制填 passing_values。不预设 60 分。多个范围匹配时使用最新确认的规则；业务结果始终优先。

创建和读取分析均须具备范围内 view 与 analyze；导出额外须 export。每次读取重新校验历史证据与当前课程记录范围；撤权不会保留旧聚合访问权。身份授权单独控制姓名及学号。

`result.calculation_version=courses-v1`。`assessment_count` 是正式有效考核记录数；`student_count` 按关联内部学生 ID 去重；`known_count=passed+failed`，`pass_rate` 为百分数，分母为零时为 null。`missing_scores` 包含空成绩；`unknown` 不等同不通过。`groups` 按课程编号、评分制度、学期分开，含实际成绩值计数 `values`（缺失独立一项），百分制 `mean` 排除空值，等级制为 null。`methodology` 保存口径说明。

证据含课程 `dependency_token=category:id:version:active`、`student_dependency_token`、原始来源批次/表单/行号/来源部门、记录版本及使用的 `rule_id`。数据摘要纳入范围内所有已关联课程（包括作废）、关联基础档案版本/内容/有效状态，能检测新增、更正、作废及基础档案变化。规则摘要纳入本学院专业所有确认版本；保守地将相关范围规则变化标记 stale。旧快照保留旧结果和证据；重新计算得到新 ID。

浏览器可复现验收：在 frontend 中设置 `AQP_TEST_PORT=8048`、`AQP_BROWSER=chrome` 后执行 `npm run test:e2e -- analysis.spec.ts`。使用临时数据库、独立合成学号 SYN-ANALYSIS-08 和课程08合成学院，finally 恢复原 grants，由 Playwright 管理服务生命周期。

## 培养环节与条件提醒（任务09，milestones-v1）

`POST /api/analyses/{category}` 支持 `courses`、`topic`、`midterm`；路径类别优先于 body，按对应类别分别检查 view/analyze。所有历史、证据、导出沿用上文统一路径，并重新检查对应类别及历史/当前记录范围。`POST /api/pass-rules` 和 GET 查询增加 `category`（默认 courses），规则独立隔离。培养环节使用 `course_code` 表示考核批次，`term` 留空。规则匹配记录所属专业、该批次、评分制度，业务通过结果优先；空专业范围只汇总当前授权专业。

Scope 可选 `grade`（基础档案入学年份）、`level`（培养层次）、`group_by`（空、grade、major、level）；课程同样支持。groups 增加 `group_value`，培养环节按考核批次/评分制度/分组分开，统计字段及分母沿用课程契约。证据 dependency_token 使用实际类别，包含基础档案版本。基础档案变动、新增、更正、作废和规则变动均使原快照 stale；结果和证据保留生成时内容。

`result.reminders[]` 给出 record_id、dependency_token、as_of、overdue 和 missing_conditions。仅合法 ISO 计划日期及实际日期，或明确 `完成状态=未完成` 可判断；缺少/无效日期显示具体缺项。未完成记录以生成日比较，不使用业务不通过推断未完成。快照时间固定，不随历史读取重算。

`POST /api/training-requirements` 使用 courses/pass_rules 独立授权，college、major、required_credits（正数）、repeat_policy=`max_passed_credits`、confirmed=true、reason 必填，追加保存操作者和时间。此明确可选规则表示每门课程只计一次，通过考核中取最大学分；仅业务确认适用后使用，未配置不猜规则。适用范围为指定学院专业所有年级/层次；空专业分析须覆盖的每个专业都有确认要求后才计算总进度。规则修改纳入课程 rule_version。`result.credit_progress` 只有完整课程范围、学分、已知通过状态、培养要求和重修规则齐全才有 value=available；students 含内部 student_id、earned_credits、progress_percent，单个专业附 requirement_id/requirement；空专业范围覆盖多个专业时返回对应的 requirement_id/requirement 列表，且每个学生的进度按其所属专业要求计算。按单课程或学期筛选不计算培养总进度；缺条件时 value=null、missing_conditions 逐项说明。培养环节快照不额外读取未经授权课程，仅提示课程学分条件不足。

浏览器验收：`AQP_TEST_PORT=8049 AQP_BROWSER=chrome npm run test:e2e -- milestone-analysis.spec.ts analysis.spec.ts`，临时库及独立 SYN-MILESTONE-09 合成数据，finally 恢复 grants。
