# 04 三级报告 PDF/Word 导出

Status: resolved

- 新增依赖 `reportlab`、`python-docx`，同步更新锁文件。
- 新模块 `backend/aqp/report_documents.py`：把三类报告数据整理为可读的标题、段落与表格，分别渲染为 PDF 与 Word。
- 三个报告导出端点增加 `format` 参数（xlsx、pdf、docx，默认 xlsx）。权限校验与 Excel 导出走同一段代码；审计目标追加格式标识；下载文件名保持 ASCII。
- 服务器缺少中文字体时，PDF 导出返回明确错误并提示改用 Word 或 Excel。
- 前端：三级报告页的三个导出入口增加格式选择。

## Answer

已实现。

- 依赖：reportlab 4.5.1、python-docx 1.2.0（连带 lxml、pillow），`pyproject.toml` 与 `uv.lock` 已同步。
- `backend/aqp/report_documents.py`：先把三类报告整理为标题、段落、表格，再分别渲染为 PDF 与 Word，两种格式文字一致。未纳入和缺失的段落照实写明原因，不留空也不填零。含学生身份信息时文档标注“敏感”，否则标注“内部资料”。
- 三个导出端点增加 `format` 参数（xlsx、pdf、docx，默认 xlsx），与 Excel 导出走同一段权限校验；审计目标追加格式；文件名保持 ASCII。服务器找不到可用中文字体时 PDF 返回 503 并提示改用 Word 或 Excel，Word 不依赖字体。
- 前端：三级报告页顶部增加导出格式选择，三个导出按钮跟随该选择。
- 文档：README、交付说明、导师课题组契约已同步。

验证：后端 11 项（三类报告 × 两种格式的文字与文件头、身份仅在授权时出现、导出授权边界、缺字体提示、字体注册）；既有报告与导出测试 10 项不受影响；浏览器用例 `report-formats.spec.ts`（三种格式的文件名与文件头、撤权后不产生下载）。单次 PDF 导出在本机约 1 秒。

## Comments
