# 04 三级报告 PDF/Word 导出

Status: ready-for-agent

- 新增依赖 `reportlab`、`python-docx`，同步更新锁文件。
- 新模块 `backend/aqp/report_documents.py`：把三类报告数据整理为可读的标题、段落与表格，分别渲染为 PDF 与 Word。
- 三个报告导出端点增加 `format` 参数（xlsx、pdf、docx，默认 xlsx）。权限校验与 Excel 导出走同一段代码；审计目标追加格式标识；下载文件名保持 ASCII。
- 服务器缺少中文字体时，PDF 导出返回明确错误并提示改用 Word 或 Excel。
- 前端：三级报告页的三个导出入口增加格式选择。

## Comments
