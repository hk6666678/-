# 01: 扩展角色与导师学生访问范围

**Status:** claimed

**Blocked by:** 无

**Specification:** ../spec.md 和 ../design-rounds.md

## Acceptance criteria

- [ ] 实现本任务对应已确认领域范围，形成数据、公开API、界面闭环。
- [ ] 当前权限、范围/身份脱敏、版本与来源追溯、审计沿用既有规则。
- [ ] API行为及关键浏览器流程有模拟验证；真实业务待验单列。
- [ ] 类型静态构建及相关回归通过，本地提交，不自行push。

## Comments

### 2026-11-12 校级角色切片

新增school_data_admin（校级数据管理员）和school_analyst（校级分析人员），兼任上限同步为5，保留platform_admin独立系统管理职责。没有隐含全校数据授权。新增公开API红绿验证创建、登录、未授权学生403、管理账号403；8项账号相关pytest、mypy25、Ruff、TS/Vite构建、Chrome账号与导航2项通过。仅本地提交。

本任务尚未完成：导师学生绑定及全部查询/分析/论文/Agent/导出原件范围重查仍待实现；不开放无范围保护的导师角色。跨学院访问仍须显式逐范围授权，不自动授予全校访问。
