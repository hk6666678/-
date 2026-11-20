# 02 导航重组与成果合并入口

Status: resolved

main.tsx 重写导航分组、page→组件映射、header 标题映射：

- 数据管理：基础导入与学生档案 / 课程导入与待关联 / 选题与中期导入 / 盲审与答辩 / **科研成果导入（新）** / **学位论文上传（新）** / 导师与课题组数据（改名换组）/ 数据纠错与维护
- 研究分析：培养过程分析（原"课程统计与通过规则"）/ 学位论文质量（新，ComparisonPanel+CandidatePanel）/ 拔尖人才模拟评价（原"人才指标模拟评价"，保留"模拟"限定词）/ 三级报告 / Agent 智能问答
- 业务规则：业务规则管理（新页，全部登录用户可见，服务端 grants 兜底）
- 系统管理（admin）：不变

新建 OutputsTabs.tsx：4 标签（科研论文/专利/获奖项目/会议）切换 category，内部 `<ResearchOutputs key={category}/>`。ResearchOutputs 组件本身不改。

## Answer

main.tsx 导航重组为 数据管理（8 项，含新 outputs/thesis_upload，mentor_groups 改名换组）/ 研究分析（5 项）/ 业务规则（新）/ 系统管理（admin）。新建 OutputsTabs.tsx（role=tab 四标签切换 category）与 ThesisQuality.tsx（ComparisonPanel onCreated → CandidatePanel 预选联动），style.css 增加 .outputs-tabs 样式。ResearchOutputs 未改。

## Comments
