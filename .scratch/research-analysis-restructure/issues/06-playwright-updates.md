# 06 Playwright 测试更新与新增

Status: resolved

- ~17 处侧栏按钮点击文案更新 + 受影响 heading 断言（navigation.spec 动态遍历兼容，核对其 2 处硬编码）。
- 6 个 spec 删"读取XX"按钮步骤（evaluation.spec 最集中，5 处）。
- 手输 ID 改 selectOption：comparisons（比较论文版本ID）、reports（导师/课题组ID）；专业筛选 fill 改 selectOption（evaluation/reports）。
- analysis.spec / evaluation.spec 中通过规则、评价规则启用步骤改到"业务规则管理"页操作。
- 新增 1 个 spec：科研成果标签页切换 + 业务规则页冒烟 + 比较生成后候选页预选联动。
- 全量 npx playwright test 通过（独立临时端口，不影响本机 8000 演示服务）。

## Answer

更新 10 个 spec：导航文案（学位论文上传/学位论文质量/培养过程分析/拔尖人才模拟评价/导师与课题组数据/Agent 智能问答/科研成果导入+tab）、删"读取XX"步骤、fill→selectOption（专业筛选、比较论文、导师）。analysis/milestone/evaluation 规则操作改到业务规则管理页（按卡片 heading 限定范围避免同名 label）。新增 restructure.spec.ts。semantic.spec 修复共享套件下的双论文 strict 冲突（独立学号+article 范围限定）。最终 AQP_BROWSER=chrome 全量两轮 25/25 通过（浏览器缓存目录被清，改用系统 Chrome channel）。

## Comments
