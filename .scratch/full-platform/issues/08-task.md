# 08: 三级报告图表与Excel

**Status:** resolved

**Blocked by:** 07

**Specification:** ../spec.md 和 ../design-rounds.md

## Acceptance criteria

- [x] 实现本任务对应已确认领域范围，形成数据、公开API、界面闭环。
- [x] 当前权限、范围/身份脱敏、版本与来源追溯、审计沿用既有规则。
- [x] API行为及关键浏览器流程有模拟验证；真实业务待验单列。
- [x] 类型静态构建及相关回归通过，本地提交，不自行push。

2026-11-13（结案）：源codex/full-08@a570bc4（功能c161c4e+审查修复73d4dd0）无冲突合入integration/aqp-trial@a13815d。新增reports.py三级报告（学生发展/导师课题组/学院学科）三GET端点+三Excel导出：全部按读取时当前权限现算，无权段落标注未纳入不计数，缺数据标注缺失不填零，一条越权记录隐藏整段计数；证据带记录/版本/年份下钻；导出要求basic export底座+每个实际纳入类别的export，课题组导出按关系三方scope×纳入类别并含空关系兜底；审计reports.read/export/denied。06的facts提取为group_facts复用（逐行等价+年份字段）。独立审查"修复后可"两项必修已落地回归：学院mentor_groups段补导师显式绑定校验（无绑定mentor不再看到关系计数）；课题组空关系导出补basic export底座。建议项采纳：pass_rule_version精确到学院+专业、空参导出文件名、roster集合提出循环。Chrome全流程（学生报告含2026真实年份标签DOM断言、课题组、学院、三份xlsx下载、550px单列）由全量套件两轮验证；Chrome运行中还抓出导入年份藏于payload.details的真实bug并修复。集成a13815d全回归：pytest142、mypy31、Ruff、build、全Chrome23/23。已知不阻塞盲区（整段隐藏分支直测、导出停用学生、课程规模性能、today时区差）记录于FULL08-CHECKPOINT.md。模拟数据验证，非真实业务验收；仅本地未push。工单结案。
