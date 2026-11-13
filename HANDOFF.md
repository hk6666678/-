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


## 06集成检查点（2026-11-13）

06源codex/full-06@ff94d6e无冲突合入integration/aqp-trial@2b4b43df6564dab56398ef4472741636747017d1，合并树与源无差异。导师课题组目录、起止关系版本、Excel预览确认、当前授权事实下钻及missing完成；工单06 tracked resolved。01-06已集成；07-10尚未开始。历史交接和全部工作树保留。独立逻辑审查无确定问题，视觉三项调整已有专项验证；真实资料/正式专家规则/真实模型效果待验，无模型外发。

集成2b4b43d本机完整检查：pytest130 passed（164.76秒）、mypy29文件、Ruff全部通过；TS/Vite build通过；全Chrome21/21（36.3秒，含mentor_groups目录/关系/事实/撤权）通过。所有启动测试和webServer进程结束，无新增常驻服务。05生成截图已还原，未知未跟踪patents-void-history.png与research-void-history.png保留不提交。最新官方额度剩短21%、周34%（单次非实时）；仅本地，未push。本文提交HEAD以git log -1核实；将基于本文最终提交预建D:/AQP-PGS-worktrees/full-07、codex/full-07，不启动实现。

## 2026-11-13 本轮预防检查点（11%，尚未上传）

最近root官方读数短used89剩11%，周剩33%。仍在处理07现有改动，非实时保证。本节为最新状态，下面保留历史。

集成integration/aqp-trial@0f4694c，完整版01–06已完成。02科研成果、03专利奖项会议、04引用日期快照及统计、05盲审答辩、06导师课题组关系事实均已合入；最终06集成130pytest、mypy29、Ruff、build、Chrome21通过。05导入中鉴权commit导致半批入库/preview500已修；02旧参与者维护越权及作废权限交集已修。真实业务输入、专家规则与获准模型效果仍待验。

唯一未合分支codex/full-07，D:/AQP-PGS-worktrees/full-07，当前f0edcf3（后续提交以git log核实）。已有模拟规则草稿/独立启用、白名单指标、证据快照、当前授权重查/stale及初步UI。261为独立快照增量迁移；极大有限权重缩放避免NaN，JSON禁止NaN。局部API、类型静态和build通过，Chrome仅覆盖模拟草稿启用，不能当完整评分流程验收。07由full07_evaluation独占，正在修学生选择/textarea/checkbox；artifacts截图留本地。

07缺口：正式规则配置及业务确认、完整雷达与成长曲线、导出、复杂指标及历史权限矩阵、完整评分UI浏览器、全回归及两轴复审。不得合并WIP或标完成。08三级报告、09Agent扩展及研究分析、10完整集成验收未开始。

共同成果/导师绑定/历史与当前范围权限交集、身份及原件独立授权继续有效。导师业务关系不自动授账号权。缺毕业延期数据标missing；引用按可选发表年份统计，旧模板兼容。模拟不当真实评价。外网抓取、训练、因果反事实、PDFWord排版与正式部署仍后续阶段。

历史全量测试服务已结束；07局部验证由代理收取并停止，最终另核实。根两张未跟踪合成截图保留不清理：.scratch/patents-void-history.png、research-void-history.png。全部旧worktree保留，git worktree list核实HEAD。

本轮只本地提交，尚未push。<=10保存检查点且停止新功能，<=5先安全停止writer、更新会话及本文件最终进度/缺口/验证/进程，再集中上传integration及full-07并核远程。未经5%或用户明确要求不得提前push。

## 2026-11-13 剩7%安全预存（仍未上传）

最新集成源码0f4694c，根预防交接a43dcbb。01–06完成；07唯一未合工作树D:/AQP-PGS-worktrees/full-07，codex/full-07@7f4f1b0。规则及评分仅模拟WIP。已修有限大权重溢出，保存与GET均55的手算回归通过，独立只读复审确认；max归一、JSON拒NaN，migration261兼容既有260。

学生改授权研究编号选择（专业筛选、当前前200条限制明确），局部Chrome/build过；历史快照列表仍补最小页面闭环，最终HEAD需重新核实。07已有6项API及模块mypy/Ruff；未做完整评价浏览器/全回归，正式配置、导出、雷达成长曲线和任务08–10未完成。artifacts截图留本地不提交；没有其他测试服务运行。

官方最近短剩7%、周32%，未到5上传线，本轮所有成果仍本地。到5先通知全部writer停、更新当前会话与本文件，再集中同步根及full07和相关成果分支，核对SHA。不得为了额度仓促合并07或伪完成。

