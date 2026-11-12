# 任务22C：隔离恢复与浏览器核验

2026-11-12，在 Windows 10.0.19045 / Python 3.12.12 / SQLite 3.50.4、真实 loopback HTTP 服务和无头 Chrome 上运行。全部为合成数据；未调用或验收真实模型。

## 可重复执行

先 `npm ci`、`npm run build`（frontend 目录），再在项目根设置 `PYTHONPATH=backend`：

```powershell
uv run python backend/tests/trial_restore.py --manifest data/trial-22b-full/report.json --output data/trial-22c-full
```

输出目录必须不存在。输入22B报告必须包含已完成的论文和分析标识并确认服务已停；22B整体状态单独保留，不能把22C通过解释为22B并发通过。禁止设置全局 AQP_ATTACHMENTS，避免附件串库。该工具仅面向已停服务的22B合成库，调用者仍须确保没有外部服务或worker写源库。

## 实际结果

- `data/trial-22c-small-2/report.json`：通过，5.082秒。源为 `trial-22b-small-4`，10学生、30课程、各20条选题及中期、2论文。
- `data/trial-22c-full/report.json`：通过，41.505秒。源为 `trial-22b-full`，1000学生、30000课程、各2000条选题及中期、100成功论文。该源22B并发分析失败，报告明确记录 `source_scale_status=failed`；22C结果独立成立。
- 两次均先通过源API新建比较、候选及一条待补充材料复核，断言复核版本1关联原论文版本；此步骤是备份前准备，不算恢复核验。
- 源API上下文退出并确认线程停止后才执行真实 `python -m aqp.backup create ... --services-stopped`，随后真实CLI恢复至不存在的隔离目录。两次CLI均返回0。
- 独立Chrome上下文带旧cookie访问恢复服务 `/api/me` 得401，清cookie后通过登录页面重新登录。
- 浏览器逐项比较恢复前后完整JSON：学生列表（前200条及总数）、首个学生档案与课程来源、首篇论文页序证据、比较、候选、复核、三类已有分析。断言JSON相等，报告保留双方SHA-256；不是只检查200或布尔值。
- 论文证据断言版本ID一致、页序为连续1..N、第一页包含合成文本；恢复论文PDF完整下载字节hash与源一致（723字节，SHA-256 `ca4186f6b2434271d587f72085eb21a8b9b90bfdfb8ae629c84321df1ef240b7`）。
- Chrome实际页面显示统一学生档案及来源部门、页序文本、已存在候选的复核意见与论文版本关联字段；保存 `restored-review.png`。浏览器和恢复服务均在运行结束退出。

初次小库浏览器尝试因工作树未构建frontend/dist，用户名控件等待超时，失败记录保留在 `data/trial-22c-small/report.json`。构建前端后重跑通过；脚本新增构建产物前置检查。最终脚本通过 `ruff check` 和 `ruff format`。

## 验收边界

这是持久化合成库的恢复验收，不是正式学生数据或专家评审验收。逐条浏览器内容比较覆盖首200学生、一个完整学生链路及一篇论文，未逐页点击1000个学生或100篇论文。CLI归档内部完整性校验覆盖全数据库及所有附件。本文不宣称所有业务UI、真实模型或22B并发分析通过。产物含合成账号数据，仅保留在本地data目录，不提交Git。
