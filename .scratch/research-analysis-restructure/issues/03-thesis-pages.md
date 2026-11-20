# 03 学位论文两页与 ID 选择器化

Status: resolved

- 数据管理·学位论文上传 = PaperPanel 原样，小改：student_id 输入后从已加载列表预填 expected_version（替换场景自动取该生当前版本）。
- 研究分析·学位论文质量：
  - ComparisonPanel：删"比较论文版本ID"数字输入与"读取标签历史"按钮，改 `<select>`（GET /api/papers，选项 `#id 标题·版本n`，无 identity 权限显示"论文（身份已隐藏）"），选中即自动加载标签历史。
  - CandidatePanel："当前比较快照ID"/"历史候选结果ID"数字输入改两个 `<select>`（GET /api/paper-comparisons、GET /api/candidate-results，挂载自动加载）。
  - 联动：main.tsx 状态提升，ComparisonPanel 生成比较后 onCreated(id) → CandidatePanel 刷新列表并预选新快照。
- 代码风格保持现有单行紧凑 JSX。

## Answer

学位论文上传页：PaperPanel 绑定学生ID onChange 自动预填该生最新版本号（identity 授权可见时）。学位论文质量页：ComparisonPanel 论文改 select（/api/papers，无 identity 显示"论文（身份已隐藏）"），选中即自动读标签；CandidatePanel 比较快照/历史结果改双 select（新列表端点，挂载自动加载），生成比较后 ThesisQuality 状态提升自动预选并提示；规则草稿/启用表单移除（见 05）。

## Comments
