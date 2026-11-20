# 04 自动加载、专业下拉与导师选择器

Status: resolved

- EvaluationPanel：挂载自动加载规则列表与历史快照；快照下拉选中即加载详情（删"读取当前授权规则""读取历史快照列表""读取快照并重查当前授权"）；学生筛选用专业下拉（复用 StudentPanel 模式：`GET /api/students?include_filters=true&limit=1` + tongjiMajors 合并），选中专业自动拉取学生（删"读取当前授权学生"）。
- ReportsPanel：同样专业下拉自动拉学生；"导师编号ID/课题组ID"数字输入改 `<select>`（GET /api/mentor-groups/directory/mentors、/directory/groups，挂载自动加载；无 identity 权限仅显示 ID）。
- AnalysisPanel：挂载自动加载分析历史（GET /api/analyses），删"读取分析历史"按钮。

## Answer

EvaluationPanel：挂载自动加载规则+历史快照+专业过滤项，规则默认选中已启用项，快照 select 选中即重查授权；专业筛选复用 include_filters+tongjiMajors 下拉，选中自动拉学生。ReportsPanel：同款专业下拉；导师/课题组改 select（目录接口返回裸数组，直接 setMentors(rows)，曾误取 .items 导致渲染崩溃已修）；select 需 aria-label 与 label 文本一致否则 getByLabel 不匹配（已修）。AnalysisPanel：挂载自动加载历史（收进折叠区），删"读取分析历史"。

## Comments
