# 09: 只读Agent扩展与研究分析

**Status:** resolved

**Blocked by:** 08

**Specification:** ../spec.md 和 ../design-rounds.md

## Acceptance criteria

- [x] 实现本任务对应已确认领域范围，形成数据、公开API、界面闭环。
- [x] 当前权限、范围/身份脱敏、版本与来源追溯、审计沿用既有规则。
- [x] API行为及关键浏览器流程有模拟验证；真实业务待验单列。
- [x] 类型静态构建及相关回归通过，本地提交，不自行push。

2026-11-13（结案）：源codex/full-09@84daec8（功能576800b+审查修复e701fdb）无冲突合入integration/aqp-trial@556344b。四个新只读Agent工具：output_statistics（四类成果、逐学生当前授权过滤、参与者三键匹配、去重与人次分口径）、mentor_group_facts（复用06 group_facts）、evaluation_snapshot（最新模拟评分摘要、明确模拟声明）、correlation_analysis（纯Python Pearson/OLS，变量白名单课程通过比例/成果数/评分总分，n<3或常数列拒绝，必带样本量/排除数/变量定义/不宣称因果局限声明；对应摘要指令强制披露并禁因果表述）。数值全部工具端计算；无模型默认明确禁用（503+界面文案）。独立审查"修复后可"唯一阻塞项（空major时evidence链接指向不同总体/403）已修：仅在显式major时给出链接且测试实际请求验证可达；建议项采纳（变量口径披露、快照键.get防御、摘要指令补忽略question指令与引用evidence_links）。审查确认权限面无越权、数学手算一致。验证e701fdb：pytest145、mypy31、Ruff、build、全Chrome23/23两轮；相关测试含r=-1/斜率-2/截距3/R2=1手算、n<3拒绝、score_total路径、链接可达、缺权403。已知未测分支与口径差异（参与者不一致在相关分析fail-closed、统计工具静默排除）记录于FULL09-CHECKPOINT.md。合成数据，非真实业务验收；仅本地未push。工单结案。
