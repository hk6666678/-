# 集成检查点（2026-11-13）

根D:/AQP-PGS，integration/aqp-trial；科研成果合并HEAD 16fe56e182046cac9fab884cad1037132cdadb3f（源codex/full-02 2e6ea6d）。本文后续文档提交HEAD以git log -1核实。

01已集成完成：导师显式绑定交集、历史分析依据撤销和Chrome保存/刷新/清空验证。02实现科研论文模板、预览确认、共同参与去重、显式更正版本、来源历史、带依据作废与筛选，作废保留payload/source/audit并退出当前统计；不提供恢复。当前scope与独立void授权专项已覆盖。引用日期快照归04后继范围。

02合并后验证：pytest 110 passed；mypy 27文件通过；Ruff通过；TS/Vite build通过；独立Chrome科研导入/历史/作废/统计/筛选流程通过（8052临时端口，服务已结束）。全Chrome e2e两次18/19：最后students测试期望ready实际duplicate:1/invalid:1；单独运行该测试1 passed，证据表明共享合成样例与前序测试顺序依赖。此现有限制未改无关代码，不能宣称全e2e通过。02双轴审查及修复信息由协调代理审查记录核实。真实学校业务、数据、专家及真实模型效果未验，无模型外发。

## 未合并成果与后续

- full05独立工作树D:/AQP-PGS-worktrees/full-05，codex/full-05，最后观察81fe2e8；仍claimed/WIP，未合，准确最新HEAD/缺口由writer HANDOFF核实。保留原成果与工作树，不触碰其开发。
- full02工作树保留；full01及历史ticket工作树全部保留，完整列表用git worktree list。
- migration210科研论文；05 migration220，research_papers/blind_reviews/defenses独立授权，学位papers及原reviews含义不变。
- 下一步由协调代理安排03/04及05最终审查集成；当前根无常驻测试服务。本轮仅合成隔离测试，未改真实data。

## 额度与同步

本轮官方账户短周期剩81%、周剩43%（单次读数非实时监控）；已恢复开发，旧5%暂停状态已过时。上轮集中同步已核实integration 9e7f7a5、full01 794c250、full02 252f2f9、full05 a85bd83。本轮新成果仅本地保存，未push。只有用户明确上传或官方任一窗口剩余<=5%时按规则先交接再集中同步。

## 集成回归收口

在dd96390之后按协调授权修复students浏览器用例共享样例冲突：仅将下载样例有效行改为该用例专属合成学号/姓名，保留错误行和全部业务断言，不改生产去重。修前全套两次失败，修后全Chrome e2e 19/19 passed（29.7秒），因此此前全套限制已解除。最后官方短周期剩78%、周剩43%。最终提交HEAD用git log -1核实；本轮未push。科研专项生成的未跟踪截图.scratch/research-void-history.png保留供核验。

## 05集成检查点（2026-11-13）

05源codex/full-05@5d7d36d，已无冲突合入integration/aqp-trial@481ef95d7ebc8b396b1e824c9c9b985d4ef8ff0d。当前文档提交HEAD用git log -1核实。独立盲审/答辩、版本评分模板与Excel模板/预览/确认、范围/身份独立授权、来源审计和UI已完成；05工单tracked且resolved。两项事务P1及批内冲突P2已修复并经独立审查。05验证记录保留在.scratch/full-platform/full05-validation.md。

03工作树D:/AQP-PGS-worktrees/full-03、codex/full-03@8388ce7为未合并WIP，等待独立审查与串行集成；根03工单仍ready-for-agent，不能视为已完成或ignored。04及后继任务未完成。保留全部历史工作树。未知未跟踪.scratch/research-void-history.png合成截图保留，不加入提交。真实学校业务/正式评分标准/专家/真实模型效果待验，无模型外发。

验证对应合并481ef95：全pytest116 passed（99.23秒）、mypy28文件、Ruff全部通过；TS/Vite build通过；独立端口8056 Chrome20/20 passed（33.8秒）。测试仅合成资料，自动生成截图已还原到分支审查版本，无生产代码追加改动。所启动pytest和Chrome/webServer进程均已结束，无新增常驻服务。额度本轮开始官方短周期剩62%、周40%（单次读数非实时）；仅本地保存未push。本文恢复合并前根HANDOFF完整内容，避免05分支过时交接代替当前记录；分支原历史仍可由git show 5d7d36d:HANDOFF.md读取。


## 03集成检查点（2026-11-13）

03已完成，取代上节03 WIP状态；codex/full-03@a7967f7无冲突合并为integration/aqp-trial@d4a850e9865b875429ebf404b98a224c649a6e69，保留05功能和所有历史。专利/获奖项目/会议独立模板、授权、公开API、导航与来源/版本/作废闭环已实现，日期严格YYYY-MM-DD及年份边界已修复审查问题。工单03为tracked且resolved。真实输入、正式规则和业务验收待验。04日期引用及06等后继未开始；01/02/03/05已集成。

浏览器验证：原全套20/20通过（36.9秒，端口8056）；browser_other_outputs.py分别patents、awards、conferences三次完整导入/统计/作废历史通过（端口8053）。这是20加3次专项，不能称playwright自动23项。TS/Vite build通过。自动覆盖的05截图已还原；本轮新合成截图.scratch/patents-void-history.png保留未跟踪（脚本各类别共用此路径，最终为会议），未知research-void-history.png仍保留。无真实资料或模型外发；仅本地，未push。

后端全回归对应d4a850e：pytest126 passed（108.68秒）、mypy与Ruff结果以下追加；当前文档提交HEAD以git log -1核实。全部测试/浏览器服务结束后交还根；下步04工作树仅预建不启动实现。

最终mypy28文件通过、Ruff全部通过；所启动进程均结束，无新增常驻服务。官方额度最新短周期剩57%、周40%（单次非实时）。将预建D:/AQP-PGS-worktrees/full-04与codex/full-04于本交接提交，不启动实现；原所有工作树保留，完整列表git worktree list。


## 04集成检查点（2026-11-13）

04源codex/full-04@f3f5d24合入integration/aqp-trial@3390ef259062b3332196abaad79e8fb4c9d8e7c3。引用日期快照、显式更正版本、Excel模板/预览/确认、身份/导师权限、整批撤权回滚、发表年份兼容和年度统计完成；工单04 tracked resolved，取代之前未开始状态。01-05已集成；06-10尚未开始。原工作树和交接历史保留。

引用专项实际为backend/tests/browser_research_outputs.py（不存在browser_citations.py），已通过保存/更正/Excel确认、2025统计及宽窄布局断言。TS/Vite build通过。只用合成资料；真实业务/专家标准/真实模型效果仍待验，无模型外发。脚本按既有行为覆盖research-void-history.png合成截图，仍保留未跟踪；patents-void-history.png同样保留。仅本地未push。

最终对应3390ef2集成检查：pytest127 passed（134.51秒）、mypy28文件、Ruff全部通过；TS/Vite构建通过、全Chrome20/20（34.6秒）及引用专项通过。所有启动的pytest/Chrome/webServer已结束，无新增常驻服务。官方额度短周期剩40%、周37%（单次非实时）。当前交接提交HEAD用git log -1核实；将基于本提交预建codex/full-06于D:/AQP-PGS-worktrees/full-06，不启动实现。

