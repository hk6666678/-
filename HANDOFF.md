# full-platform02 检查点

分支 codex/full-02；基础9e62e2d；实现提交edf2851、52d1bf2、e53a57b，后续Chrome验证提交见git log。

科研论文独立research_papers授权类别和research_outputs模块，migration210。xlsx v1模板/preview/confirm、共享参与次序角色、业务键去重、显式版本变更、待关联、来源审计和受全参与者identity/view限制的history API；列表支持导师显式绑定交集、当前学生college/major/name核对，统计个人参与和可见成果去重。

页面ResearchOutputs支持上传预览确认、显式变更勾选、列表和统计，导航及授权类别已接。npm ci后tsc/vite build通过。后端research+authorization+student_binding+mentor_records 8 passed；模块mypy/ruff通过。新增Chrome合成数据登录→科研页面→上传preview→confirm→成果和统计显示通过（browser_research_outputs.py）。全部测试使用临时合成DB，真实data未动。

未验/未完：没有作废API/页面；history仅API，页面未展示来源/历史；未提供引用日期快照字段；导师绑定与跨学院共享参与者完整矩阵专项新增测试仍不充分（继承绑定回归通过）；浏览器只验证单人导入及统计，未验共享/越权/变更。不得宣称完整02全部验收。真实业务验收待真实模板与资料。

无遗留服务进程，Chrome fixture已finally关闭uvicorn和浏览器。禁止push，当前仅本地保存。最后官方quota短12%周48%（父代理后续报告11%），需继续按规则检查。

# 完整平台当前检查点（2026-11-12）

本文件取代此前额度停止交接的过时状态。当前已完成安全检查点，不再开始新功能，最近官方短周期剩6%、周剩47%；尚未达到5%停止线，尚未触发本轮GitHub上传。

## 集成与已完成

根 D:/AQP-PGS，integration/aqp-trial，功能HEAD5698851（后续交接文档提交以git log -1核实）。full01导师显式绑定交集完整集成：9e62e2d合794c250；c6faaa7历史分析GET/evidence绑定撤销测试；5c77545绑定管理Chrome保存/刷新持久化/清空撤销专项及启用文案；5698851领取02/05。

验证：9e62e2d全后端103 passed；c6faaa7专项3 passed；mypy26、Ruff、TS/Vite、Chrome账号导师兼任创建及绑定管理专项通过。真实学校数据、导师对应关系、学校业务规则及专家验收未做。01本轮部分先实现后补测试，不能称严格TDD。

## 正在开发、不能合并宣称完成

- D:/AQP-PGS-worktrees/full-02，codex/full-02，HEAD 252f2f9（b92b0a2之后双轴审查修复）（前edf2851/52d1bf2/e53a57b）。科研论文独立于学位papers；migration210，Category research_papers。后端模板/preview确认/业务键共享参与/去重及显式变更版本/history/待关联审计，相关回归8项及模块mypy/ruff通过；伪学院和当前学生迁学院约束测试补齐。UI上传预览确认/列表个人参与与范围去重统计/导航已实现，build通过，隔离Chrome登录上传预览确认与统计显示通过。WIP缺口：void、history/来源页面、引用日期快照、充分共享及mentor授权矩阵、最终全回归及双轴审查。未合并，不宣称完整02。分支自带HANDOFF，无运行进程。
- D:/AQP-PGS-worktrees/full-05，codex/full-05，HEAD a85bd83（前09899e0）。独立盲审答辩创建/列表、模拟模板持久化、全体covered_student_ids授权、来源及原文download和identity分离、duplicate/conflict/即时撤权，5相关API测试+模块mypy/ruff通过。WIP缺口：Excel预览确认、模板管理完整版本流程、UI/browser、最终全回归与审查。未合并，不宣称完整05。分支自带HANDOFF，无运行进程。
- 其他历史worktrees均保留；git worktree list核实全部，只有codex/full-02/full-05尚未合当前integration。full-01 HEAD794c250已合。

## 固定决定与下一步

1. 02 migration210_research_outputs.sql，05 migration220_external_assessments.sql；类别research_papers/blind_reviews/defenses分别授权，学位papers和旧优秀普通复核reviews语义不变。
2. 新领域无自动模型外发，现有模型purpose仍仅agent/papers。共同成果按当前可见参与范围展示，不泄露隐藏身份；个人参与和范围去重分开；导师兼任仍受绑定交集。
3. 继续两模块公开API/界面/Chrome完整验证；没有完成不强行合并WIP。额度<=10%先各自保存准确commit及缺口，<=5%停止writer、保存本交接和工作树再集中上传integration及相关WIP分支核实SHA。
4. 本轮没有改真实data；新测试均为合成fixture。当前无长期后台服务由协调代理启动，测试临时webserver结束自动清理；各writer进程最后另核实。

## 同步

origin核实为https://github.com/hk6666678/-.git；本轮仅本地保存，尚未push。停止线时按docs/agents/github-sync.md，先检查无密钥/真实业务数据再普通push并ls-remote核实，禁止force。

## 最后只读审查与修复

02双轴均发现同一P1：替换同DOI成果只检查新参与者，可删除无权旧参与者。252f2f9在preview和confirm都重新校验旧payload全体维护权限；公开API测试先200失败再403通过，科研专项4 passed，模块ruff/mypy通过。仅修现有缺陷，未增加功能，未合integration。最后quota6%仍高于5%，安全结束本轮，无push；不为压到5而消耗。

## 官方5%停止线与集中同步

2026-11-12 root再次读取get_usage_limits：短周期used95%，剩5%；周剩47%。所有writer已在干净本地提交停止，无测试服务遗留。现停止新增开发，按规则集中同步integration/aqp-trial、codex/full-02、codex/full-05及full-01来源分支。02/05未合并仍为WIP，进度/缺口/决策见上文。同步结果以本轮会话在线核对为准，失败不可声称已上传。


集中同步已成功：在线ls-remote核对integration为9e7f7a5、full-01为794c250、full-02为252f2f9、full-05为a85bd83，与本地一致。此补记单独本地提交后同步集成分支；代码与其他分支不变。停止开发，等待额度恢复或用户另行安排。

