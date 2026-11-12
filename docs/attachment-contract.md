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

## 论文版本与基础特征（任务11）

`POST /api/papers` 接收 multipart `file`（PDF，最大20MB）、`student_id`、`title`、`level`、`discipline`、`year`、`expected_version`、`covered_student_ids`（全体学生ID JSON数组）。后三项元信息可空，空值表示缺失，不推定论文对照组。版本按学生递增，冲突409；授权全部通过后才写业务数据。扫描、加密或损坏PDF仍保留受控原件，由worker记录失败。

`GET /api/papers` 返回当前范围内版本状态、基础计数及明确“未提取”的语义状态。无全体身份权限不返回标题、学生ID、文件名或正文。`POST /api/papers/{id}/retry` 仅重排失败版本；替换上传新版本。历史版本引用不变。

`GET /api/papers/{id}/evidence` 返回 `version_id` 与本地结果：`pages[{page,text}]`、`sections[{page,text}]`、`references[{page,text}]`，page 始终是1起始PDF文件页序；`page_count/character_count/section_count/reference_count` 为基础统计。章节按行首编号识别，参考文献按参考文献标题之后非空行识别，计数是行数而非经过语义归并的文献条数。语义特征、研究问题、方法和创新主张尚未提取，属于任务13。证据读取和 `/download` 每次重查papers查看、全体身份、原始下载授权，并校验原件hash，不提供静态文件链接。

独立命令 `python -m aqp.paper_worker`；`--once` 单次驱动，`--lease-seconds` 可配置恢复等待（默认60秒）。SQLite原子领取及token围栏保证多worker仅有一次有效发布；进程中断后任务保留processing，租约过期后重新领取。结果与完成状态同一事务提交，重试不新增论文版本。`Start-Aqp.ps1` 隐藏启动自有worker并在服务退出时清理；重复运行的worker由数据库领取互斥，过期worker不能覆盖新token结果。数据库与attachments须成套备份。

## 智能论文特征（任务13）

`POST /api/papers/{version_id}/semantic` 在本地解析成功后同步执行一次智能提取；调用前需文件涉及全体学生的 papers maintain/view/identity/download 权限，返回前再次检查读取权。`GET` 同路径需全体 view/identity/download，返回 `{items:[...]}` 历史（新到旧）。两者均校验原件完整性，拒绝访问沿用脱敏审计。

130迁移 `paper_semantic_runs` 独立保存每次尝试，不改写本地解析与旧结果。结果包含id、version_id、file_version、sha256、model、model_config_version、parser_config、四类features和明确独立的expert_evaluation未提供状态。特征status为available/missing/failed/disabled；available保留text/page/quote，quote必须在对应1起始PDF文件页原文中逐字存在。结果整体disabled/failed/partial/succeeded；部分缺失或失败不能宣称完整成功。模型配置变更期间的结果拒绝接受。

无获准模型时保存disabled尝试并保留本地结果。失败可重试，历史持续保留；错误不保存模型异常正文。不截断全文后声称完整分析。源文仅作为不可信数据输入，不能改变权限或触发工具。原文引文校验只验证出处，不证明模型概括或学术判断正确；真实效果须实际获准模型人工抽检。
