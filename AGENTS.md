## Agent skills

### Issue tracker

任务和规格使用本地 Markdown；创建、读取或更新任务时，参阅 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个默认 triage 标签；分诊或更新任务状态时，参阅 `docs/agents/triage-labels.md`。

### Domain docs

采用 single-context 布局；探索代码或讨论领域概念前，参阅 `docs/agents/domain.md`。

### 额度与跨模型交接

开发前、长任务期间及任务切换时，按 `docs/agents/quota-handoff.md` 检查官方额度；剩余达到 5% 及以下时先在当前会话整理并保存交接摘要，再停止开发。

### GitHub 提交与同步

每个功能验证并提交后，以及额度交接前，按 `docs/agents/github-sync.md` 将对应成果分支同步到用户指定的 GitHub 仓库，核实推送结果；远程地址或认证缺失时明确告知用户。
