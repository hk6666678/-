# 02: 科研论文与共同参与成果导入

**Status:** resolved

**Blocked by:** 01

**Specification:** ../spec.md 和 ../design-rounds.md

## Acceptance criteria

- [x] 实现本任务对应已确认领域范围，形成数据、公开API、界面闭环。
- [x] 当前权限、范围/身份脱敏、版本与来源追溯、审计沿用既有规则。
- [x] API行为及关键浏览器流程有模拟验证；真实业务待验单列。
- [x] 类型静态构建及相关回归通过，本地提交，不自行push。

## Answer
已合integration 16fe56e（源2e6ea6d），科研导入、更正、历史、作废、scope/identity/mentor授权闭环完成。根110 pytest、mypy27、Ruff、build及科研Chrome通过。全e2e现有限制：18/19，students共享样例重复顺序依赖，单跑通过；真实学校业务待验。引用快照归04。仅本地保存。


集成补验：经授权隔离students测试专属合成样例后，全Chrome e2e 19/19通过；此前顺序依赖已解除。生产逻辑未改。
