# 05: 选题与中期导入

**Status:** resolved

**Specification:** [AQP-PGS 第一版开发规格](../spec.md)

**What to build:** 分别导入选题和中期模板，在学生档案查看对应批次成绩与信息。

**Blocked by:** 03 基础信息导入与学生档案

**规格覆盖:** 用户故事 7、9、10、11、15、16、18、20、25；AC02、AC03、AC05、AC06、AC07。

## Acceptance criteria

- [x] 实现两类独立版本模板，按学号＋培养环节＋批次识别，选题标题、评分制度等按规格校验。
- [x] 支持预览确认、错误保留、重复跳过、内容变化待确认及缺基础档案待关联。
- [x] 档案按环节和批次展示，附件缺失不阻塞基本信息及成绩入库；重复批次冲突不静默覆盖。
- [x] 在本任务涉及的页面、公开 API 和持久化行为间完成可演示闭环，权限与审计随该功能一起交付。
- [x] 使用已确认测试边界验证外部行为；测试数据清楚标为合成，测试替身不计真实模型验收。

## 实现约束

遵循 AQP-PGS 第一版开发规格、项目术语和架构决策；不扩大第一版范围。涉及的修订、证据与原始文件不得静默覆盖。本任务拆分已于 2026-11-11 经用户确认发布。任务可执行性取决于前置任务及注明的外部条件，不由分诊标签单独决定。


## Answer

实现完成，合成数据功能验证通过；真实业务验收待真实样例核对。独立 topic/midterm v1 Excel 模板，预览确认、错误保留、待关联、身份与范围冲突、重复跳过和多批次保留。基础档案补齐触发范围核对自动关联，档案展示环节与来源。缺成绩和附件均不阻塞合法记录。

稳定数据契约：milestone_records.id 为后续附件与修订的记录标识；category、assessment_batch、student_id、source_row_id、payload、version、active。共享 import_batches/import_rows 保留原始文件与行；normalized_json 使用学号、姓名、考核批次、评分制度、原始成绩、所属学院、专业等标准字段。

公开API：GET /api/templates/milestones/{category}；POST /api/milestones/{category}/preview；GET /api/milestone-imports/{id}；POST /api/milestone-imports/{id}/confirm；GET /api/milestones（支持student_id与分页）；基础档案详情 milestones 字段。评分制度支持百分制、五级制、二级制；内容变更保留conflict供06/07处理。

验证：API公共边界5条测试；浏览器合成选题模板下载、上传预览与确认闭环；mypy、ruff、TypeScript/Vite构建。最终整体验证记录见交付消息。
