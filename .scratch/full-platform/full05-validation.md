# full05 本机模拟验证

- 设计brief：学院管理人员集中维护盲审/答辩；沿深色固定导航、浅色表格，突出Excel预览、行号错误及确认；无真实模型。
- Chrome合成流程：错误quality=101→行号2错误且禁止确认→修为85重新预览→确认→R01记录可见。截图frontend/test-results/assessment-error.png、assessment-confirmed.png（运行产物未提交）。
- 截图自查：移除重复标题；导航当前项清晰，错误原因与操作可读。非独立视觉评分。
- API：模板草稿不可覆盖；维护不隐含启用；activate_templates独立授权；业务确认人/依据/录入人时间可追溯；已引用历史不覆盖。
- 验证：external_assessments+authorization 8 pytest通过，Ruff通过，mypy2模块通过；TS/Vite build通过，Chrome专项1通过。
- 仍为合成验证；真实资料、正式评分标准及真实业务验收待输入。未使用真实模型。

## integration合并后最终回归

合并基线b05c06f后，完整后端116 pytest通过（166.29秒）、全backend Ruff通过、mypy28模块通过、TS/Vite构建通过。Chrome20/20通过（32.3秒）；考核用例使用专属合成学生并finally恢复原授权，避免跨测试污染。最终仅测试隔离与截图路径有后续提交，无生产代码变化。
固定截图：.scratch/full-platform/screenshots/assessment-error.png、assessment-confirmed.png；成功截图已view_image自查，标题不重复、导航当前项与分项成绩可读。合成验证不等同真实业务验收。
