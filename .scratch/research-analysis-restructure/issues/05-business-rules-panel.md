# 05 业务规则管理页

Status: resolved

新建 frontend/src/BusinessRulesPanel.tsx，集中迁移三处规则管理代码（逻辑不变，仅迁移）：

1. 通过规则 + 培养要求表单/历史（原 AnalysisPanel.tsx 折叠区"业务确认通过规则（独立授权）"）；
2. 评价规则草稿表单 + 独立授权启用表单（原 EvaluationPanel，EvaluationPanel 保留只读规则下拉供评分选择）；
3. 候选规则草稿 + 逐条启用表单（原 CandidatePanel，CandidatePanel 保留规则只读列表）。

各区块列表挂载自动加载。原三个面板移除对应写操作区后不再含规则写操作。

## Answer

新建 BusinessRulesPanel.tsx，三个自包含子组件：PassRules（通过规则+培养要求，含规则环节/学院/专业/课程/学期独立输入）、EvaluationRules（草稿+独立授权启用，迁移原 EvaluationPanel 两块）、CandidateRules（草稿+逐条启用，迁移原 CandidatePanel）。列表挂载自动加载。AnalysisPanel/EvaluationPanel/CandidatePanel 对应写操作区已移除，各留指向说明。

## Comments
