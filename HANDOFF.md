# 完整平台当前检查点（2026-11-12）

本文件取代此前额度停止交接的过时状态。当前仍在工作，最近官方短周期剩13%、周剩48%；尚未达到5%停止线，尚未触发本轮GitHub上传。

## 集成与已完成

根 D:/AQP-PGS，integration/aqp-trial，当前HEAD5698851。full01导师显式绑定交集完整集成：9e62e2d合794c250；c6faaa7历史分析GET/evidence绑定撤销测试；5c77545绑定管理Chrome保存/刷新持久化/清空撤销专项及启用文案；5698851领取02/05。

验证：9e62e2d全后端103 passed；c6faaa7专项3 passed；mypy26、Ruff、TS/Vite、Chrome账号导师兼任创建及绑定管理专项通过。真实学校数据、导师对应关系、学校业务规则及专家验收未做。01本轮部分先实现后补测试，不能称严格TDD。

## 正在开发、不能合并宣称完成

- D:/AQP-PGS-worktrees/full-02，codex/full-02，checkpoint52d1bf2（前edf2851）。科研论文独立于学位papers；migration210，Category research_papers。后端模板/preview确认/业务键共享参与/去重及显式变更版本/history/待关联审计，8相关测试及模块mypy/ruff通过。UI上传预览确认、列表统计及导航已写且build通过，部分未提交；伪学院/迁学院专项与Chrome仍在补，尚未最终集成回归/审查。
- D:/AQP-PGS-worktrees/full-05，codex/full-05，checkpoint09899e0。独立盲审答辩创建/列表、模拟模板及全体covered_student_ids授权，2API测试+ruff通过。完整写入/重复/撤权/原文分离测试、评分模板版本持久化、Excel与UI尚在开发，不能视作闭环。
- 其他历史worktrees均保留；git worktree list核实全部，只有codex/full-02/full-05尚未合当前integration。full-01 HEAD794c250已合。

## 固定决定与下一步

1. 02 migration210_research_outputs.sql，05 migration220_external_assessments.sql；类别research_papers/blind_reviews/defenses分别授权，学位papers和旧优秀普通复核reviews语义不变。
2. 新领域无自动模型外发，现有模型purpose仍仅agent/papers。共同成果按当前可见参与范围展示，不泄露隐藏身份；个人参与和范围去重分开；导师兼任仍受绑定交集。
3. 继续两模块公开API/界面/Chrome完整验证；没有完成不强行合并WIP。额度<=10%先各自保存准确commit及缺口，<=5%停止writer、保存本交接和工作树再集中上传integration及相关WIP分支核实SHA。
4. 本轮没有改真实data；新测试均为合成fixture。当前无长期后台服务由协调代理启动，测试临时webserver结束自动清理；各writer进程最后另核实。

## 同步

origin核实为https://github.com/hk6666678/-.git；本轮仅本地保存，尚未push。停止线时按docs/agents/github-sync.md，先检查无密钥/真实业务数据再普通push并ls-remote核实，禁止force。
