# 附件及证据访问契约（任务10／11）

`aqp.attachments.storage_root(db_path)` 默认使用数据库父目录的 `attachments/`，可用 `AQP_ATTACHMENTS` 指定受控本地目录。该目录不得发布为静态资源，数据库与目录须成套备份。测试数据库使用临时父目录，文件随测试清理。

100 迁移保存不可覆盖 `attachment_versions`：稳定 `id`、`milestone_id`、递增 `version`、随机 UUID `relative_path`、SHA-256、原始文件名、类型、长度、上传账号、时间、`covered_student_ids`。文件名仅是元数据，不能作为读取路径。原文件独立保留，不执行嵌入内容或文档指令。

范围由来源维护者核对并显式声明，系统不自动识别全文中的全部身份。声明必须包含绑定学生，每个声明 ID 必须对应有效正式档案，上传逐个检查维护与身份权。维护者应在上传前将文中涉及的全部学生加入声明；无法核对时不要上传。该限制在界面和本说明展示，声明随版本保存以便审计。待关联记录不能以来源学号推定身份，须先核对关联。

API：
- `GET /api/milestones/{id}/attachments`：历史；无文件全体身份／查看权不展示文件名。
- `POST /api/milestones/{id}/attachments`：multipart `file`、`expected_version`、`covered_student_ids`（JSON整数数组）。冲突409，格式错误422，权限不足403。成功返回版本ID、版本、文件名、hash、长度、时间、上传者。
- `GET /api/attachments/{version_id}/download` 与 `/preview`：每次根据当前有效授权检查绑定学生及文件全体学生的环节查看、身份、原始下载权。预览只返回惰性纯文字，React文本显示，不注入HTML。历史版本沿用同样授权。

可复用公共边界：`authorize_students(db, actor, category, ids, operations)` 验证全体正式身份与当前范围；`storage_root(path)` 定位目录；`read_version_blob(root, row)` 校验路径、文件存在、hash后读取。调用读取前必须按实际类别与覆盖范围授权。任务11可在论文版本表沿用相同字段，并用 papers 类别授权；不得通过论文证据链接绕开身份／下载权限。

原件完整性不符返回409，不提供损坏内容。上传、历史、下载、预览有审计；拒绝授权有脱敏审计，不记录文件正文。原件读取不走静态目录，附件不得放入 frontend/dist。
