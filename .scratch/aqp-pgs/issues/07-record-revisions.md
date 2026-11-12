# 07: 差异确认、更正与作废

**Status:** resolved

**Specification:** [AQP-PGS 第一版开发规格](../spec.md)

**What to build:** 查看已有记录的新旧差异，确认更正或按原因作废并查看历史。

**Blocked by:** 06 在线纠错与身份确认

**规格覆盖:** 用户故事 19、21、22；AC06、AC08、AC12。

## Acceptance criteria

- [x] 四类业务记录均支持同键变化差异确认，保留原值、新值、来源与操作者；身份字段转人工身份确认流程，不自行合并。
- [x] 基于当前预期版本确认，期间被其他用户修改则提示冲突，不能覆盖后续修订。
- [x] 作废要求权限和原因，退出当前有效数据集但保留历史；无物理删除及整批回滚能力。
- [x] 提供可供分析依赖追踪的数据修订标识，并通过公开 API 与历史页面验证。
- [x] 在本任务涉及的页面、公开 API 和持久化行为间完成可演示闭环，权限与审计随该功能一起交付。
- [x] 使用已确认测试边界验证外部行为；测试数据清楚标为合成，测试替身不计真实模型验收。

## 实现约束

遵循 AQP-PGS 第一版开发规格、项目术语和架构决策；不扩大第一版范围。涉及的修订、证据与原始文件不得静默覆盖。本任务拆分已于 2026-11-11 经用户确认发布。任务可执行性取决于前置任务及注明的外部条件，不由分诊标签单独决定。


## Answer

基于已有未提交实现补齐：保留 records.py、070_records.sql 以及授权扩展的合理结构，补齐四类公开 API 验证、正式记录 RecordPanel、独立合成浏览器用例和课程作废过滤。没有重建或清空已有成果。

- GET `/api/records/{category}` 支持 include_void、offset、limit；GET `/api/records/{category}/{id}` 返回当前版本、修订历史和 dependency_token。
- POST `preview` 接受 expected_version、字段更正、reason 和人工 identity_confirmed，返回不可变 proposal_id 与新旧差异；POST `confirm` 再次核验 proposal 所属人、当前授权和 expected_version。冲突返回409，不覆盖后续修订。
- POST `void` 需要独立 void 授权、非空原因、confirmed=true 和 expected_version，保留内容并增加修订版本；有效课程/选题/中期列表排除作废记录。
- dependency_token 格式 `category:id:version:active`，可供后续分析保存依赖快照。原始 import_rows 未被覆盖；修订保留前值、后值、来源批次/行/部门、操作者、时间与依据。身份更改需人工依据和身份权限，禁止移动正式业务记录的学号归属或合并其他学生。
- 数据维护与作废分别授权；读取历史逐版本检查范围并脱敏。基础档案/课程/选题/中期均有公开 API 行为用例。

验证：严格 mypy、Ruff、完整 pytest 45 passed；TypeScript/Vite build；Chrome（AQP_TEST_PORT=8047）全部11个浏览器用例通过。合成验证不等于真实业务数据验收。浏览器新增用例使用独立合成学号，授权 finally 恢复。

已合并 integration/aqp-trial 的 e127ab3 到本任务分支；未合入根工作树，未删除工作树。
