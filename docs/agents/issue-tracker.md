# Issue tracker: Local Markdown

任务和规格保存在 `.scratch/`，每个功能一个目录：

- 规格：`.scratch/<feature-slug>/spec.md`
- 任务：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 01 编号，每个任务一个文件。
- 分诊状态：文件顶部的 `Status:` 行，使用 `triage-labels.md` 中的标签。
- 评论：追加到文件底部的 `## Comments` 下。

技能要求“发布到任务跟踪系统”时，在对应功能目录创建文件。
要求“获取任务”时，读取用户指定路径或编号对应的文件。

## Wayfinder

- 地图：`.scratch/<effort>/map.md`，包含 Notes、Decisions-so-far、Fog。
- 子任务：`issues/NN-<slug>.md`；正文记录问题，`Type:` 使用 research/prototype/grilling/task。
- 依赖：顶部 `Blocked by: NN, NN`；所有依赖均为 resolved 后才可开始。
- 领取：按编号选择开放、无阻塞且未领取的任务；开始工作前保存 `Status: claimed`。
- 完成：在 `## Answer` 下追加答案，设置 `Status: resolved`，并将摘要和链接追加到地图的 Decisions-so-far。
