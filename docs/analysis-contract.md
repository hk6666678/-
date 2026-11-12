# 分析与证据 API 契约（课程 v1）

任务 09、17、19 的只读消费者可使用此契约；认证、CSRF 与统一授权沿用现有 API。业务管理员身份不提供隐含数据权限。

- `POST /api/analyses/courses`：`college`、`major` 必填；`course_code`、`term` 可选，空表示范围内全部。每次生成新快照，返回独立 `id`，不覆盖历史。
- `GET /api/analyses`：仅返回当前仍有权读取的历史快照。
- `GET /api/analyses/{id}` 和 `/{id}/evidence`：返回 `category`、`scope`、`created_at`（Unix 秒）、`data_version`、`rule_version`、`stale`、`result`、`evidence`。两条读取路径内容相同。
- `GET /api/analyses/{id}/export`：同一快照的 JSON 导出边界，额外检查 export；供任务 19 的 Excel 导出消费。证据按当前 identity 授权脱敏，原快照保持不变。
- `GET /api/pass-rules?college=...&major=...`：规则历史；`POST /api/pass-rules`：业务确认后追加版本，独立检查 courses/pass_rules。规则包含学院、专业、课程、评分制度、可选学期、确认依据、操作人和时间。百分制填 threshold；等级制填 passing_values。不预设 60 分。多个范围匹配时使用最新确认的规则；业务结果始终优先。

创建和读取分析均须具备范围内 view 与 analyze；导出额外须 export。每次读取重新校验历史证据与当前课程记录范围；撤权不会保留旧聚合访问权。身份授权单独控制姓名及学号。

`result.calculation_version=courses-v1`。`assessment_count` 是正式有效考核记录数；`student_count` 按关联内部学生 ID 去重；`known_count=passed+failed`，`pass_rate` 为百分数，分母为零时为 null。`missing_scores` 包含空成绩；`unknown` 不等同不通过。`groups` 按课程编号、评分制度、学期分开，含实际成绩值计数 `values`（缺失独立一项），百分制 `mean` 排除空值，等级制为 null。`methodology` 保存口径说明。

证据含课程 `dependency_token=category:id:version:active`、`student_dependency_token`、原始来源批次/表单/行号/来源部门、记录版本及使用的 `rule_id`。数据摘要纳入范围内所有已关联课程（包括作废）、关联基础档案版本/内容/有效状态，能检测新增、更正、作废及基础档案变化。规则摘要纳入本学院专业所有确认版本；保守地将相关范围规则变化标记 stale。旧快照保留旧结果和证据；重新计算得到新 ID。

浏览器可复现验收：在 frontend 中设置 `AQP_TEST_PORT=8048`、`AQP_BROWSER=chrome` 后执行 `npm run test:e2e -- analysis.spec.ts`。使用临时数据库、独立合成学号 SYN-ANALYSIS-08 和课程08合成学院，finally 恢复原 grants，由 Playwright 管理服务生命周期。
