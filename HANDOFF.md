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
