# 任务22合成试用验收

本次仅验证软件与合成数据，真实资料、业务规则和获准模型效果属于任务23。没有启用外部模型或外部追踪。详细实测见 trial-validation-scale.md、trial-validation-restore.md。

## 复现步骤

按根README安装和构建；使用隔离合成目录，先清除AQP_ATTACHMENTS。PowerShell设置 PYTHONPATH=backend、PYTHONUTF8=1，用本机Python依次执行：

```powershell
.venv/Scripts/python backend/tests/trial_scale.py --small --output data/check-small
.venv/Scripts/python backend/tests/trial_scale.py --output data/check-full
.venv/Scripts/python backend/tests/trial_samples.py --templates data/check-full --output data/check-samples
.venv/Scripts/python backend/tests/trial_restore.py --manifest data/check-full/report.json --output data/check-restored
```

目录必须不存在。工具创建并关闭隔离HTTP服务；备份前仍须确保没有外部worker/服务写该库。原始业务数据不可用于此工具。产物仅本机data保留，Git只提交合成工具和脱敏报告。系统日常启动、账号创建见README；备份维护见backup-restore.md。

## 证据映射

以下为公开API测试及浏览器流程的文件映射；不表示每个AC只有一个测试，也不把代码存在视为验证通过。

| AC | 后端测试（backend/tests/） | 浏览器（frontend/tests/）或实测 |
|---|---|---|
|01、09|test_accounts、test_authorization、test_students、test_agent|accounts、authorization、students、agent|
|02–05|test_students、test_courses、test_milestones、test_resolution、test_import_category_boundaries、test_trial_samples|students、courses、milestones、resolution|
|06–08|test_records、test_resolution、test_courses、test_milestones|records、resolution|
|10–12|test_analysis、test_milestone_analysis、test_trial_samples|analysis、milestone-analysis|
|13–14|test_attachments、test_papers、test_backup|attachments、papers；22C真实CLI恢复|
|15|test_paper_semantics、test_papers、test_agent_paper|semantic；替身/禁用状态，真实语义效果待23|
|16–18|test_comparisons、test_candidates、test_reviews|comparisons；22C候选复核页面及版本关联|
|19–21|test_agent、test_agent_paper、test_model_connection|agent、model；真实模型效果待23|
|22|test_exports、test_attachments|exports、attachments|
|23|test_audit_viewer、test_authorization、test_analysis、test_exports、test_agent|audit、authorization、analysis、exports：撤权即时生效、旧快照保留/过时、审计权限|
|24|trial_scale、trial_scale_concurrency|真实HTTP五账号分析；见规模报告|
|25|test_backup、trial_restore|CLI成套恢复+Chrome来源/证据/复核+PDF字节校验|

## 本轮结果及边界

- 四类模板小样本与缺学号错误文件从系统模板生成；手算8条考核为4通过、2不通过、2未知，66.67%。data/trial-22a-package含对应Excel与独立expected.json。发行包现含四类别各自缺学号、缺列、格式、重复、姓名冲突、版本错误、不可解析、同键变化文件；公开API逐一断言422或invalid/duplicate/conflict。CLI实际生成data/check-samples共36个Excel及expected.json，3项相关测试通过。
- 全量1000学生/30000课程/各2000选题中期/100论文实际核对通过；五账号分析首次3/5锁超时失败，修复后5/5成功。60秒有界等待仅作用分析创建，保留一致性；实测请求7.468–36.842秒，不能作为更大规模性能承诺。
- 最终全量规模70.935秒，恢复41.509秒。恢复JSON对比覆盖前200学生及一个完整学生链、一篇论文和三类分析、比较、候选、复核；CLI校验完整库与附件。未逐页面点击全部1000学生或100论文。
- Chrome完整17项通过（27.5秒）；前端TypeScript/Vite构建通过。后端最终检查结果见任务22记录。
- 两轴审查发现同一附件环境变量隔离问题，已补公开子进程红绿验证并修复；旧872行草稿删除但保留Git历史。验证入口分为小样本、规模、并发回放、恢复，未新增生产功能框架。

## 未完成

软件合成验收已完成；两轴抽查未发现剩余阻断。真实业务验收仍未完成，不能把本轮规模/恢复通过说成真实业务交付完成。13真实语义模型、23真实资料/专家规则/获准模型待验；21恢复浏览器链已由22C完成模拟验证。

最终本地复验：`python -m pytest -q` 93 passed in 77.80s；`python -m mypy` 25文件通过；`python -m ruff check .`通过；`npm --prefix frontend run build`通过。小规模CLI与发行包CLI实际运行成功。
