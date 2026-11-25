# AQP-PGS 学院试用版

已确认模拟完整版范围已实现并完成合成验收（[任务10复现与限制](FULL10-CHECKPOINT.md)）：多学院与导师显式绑定、四类科研成果及引用日期快照、盲审答辩、导师课题组、模拟评分与三级报告；另保留四类Excel导入纠错、统一档案、培养分析、论文解析与比较、候选复核、只读Agent、导出、审计和备份恢复。真实模型默认未启用，真实业务验收待资料与获准服务。详见 [交付说明](docs/trial-demo.md) 和 [验收记录](docs/trial-validation.md)。

登录后进入“授权与脱敏验证”：平台管理员选择账号，按数据类别、操作、学院与专业添加或撤销授权；专业留空表示该学院全部专业。维护、查看、分析、身份展示、导出、原始下载、通过规则、标签、候选规则启用及复核分别配置。下方按钮以当前账号查询三个明确标注的合成样例，演示范围隔离与身份隐藏，不写入真实学生档案。授权更改带版本冲突检查和幂等标识，并记录变更前后内容；后续请求直接读取当前授权。

“数据纠错与维护”页可按学院和专业做数据一致性核对：交叉比对不同来源部门对同一学生登记的学院专业、姓名、论文信息、指导关系和日期，只报告差异、不改动记录，无查看权限的来源标注为未核对。同页给出公开、内部、敏感三级数据分级的建议映射，待业务确认。三级报告可导出 Excel（全部字段与证据）或排版后的 PDF、Word；PDF 依赖服务器上的中文字体。

## 安装与启动

要求 Windows PowerShell、uv、Node.js 22.12 以上。依赖已锁定；数据默认保存在本机 data 目录，不提交到 Git。

```powershell
uv sync --locked
cd frontend
npm ci
npm run build
cd ..
$env:PYTHONPATH = 'backend'
$env:PYTHONUTF8 = '1'
.venv\Scripts\python -m aqp.cli bootstrap --username admin
.\Start-Aqp.ps1
```

初始化时交互输入两遍 12～128 字符密码，不通过命令参数传递密码；没有默认密码。平台已有账号后禁止再次初始化。打开 http://127.0.0.1:8000 ，登录后进入“个人账号管理”，创建个人账号、调整角色或停用。角色修改会撤销该账号已有会话；禁止移除最后一位有效平台管理员。

数据位置可通过 AQP_DB 环境变量指定，迁移通过 `.venv\Scripts\python -m aqp.cli migrate` 显式执行，服务启动也会应用未执行的版本迁移。本机启动脚本只监听回环地址；服务器部署及 HTTPS 配置属于后续部署工作。

## 开发与验证

涉及模型调用、Agent 权限或论文引文的改动，先运行离线验收：

```powershell
.\tools\Test-ModelAcceptance.ps1
```

该入口使用模型替身和临时资料，检查普通业务库的外发拦截、Agent 摘要前撤权及 409 审计、双页 PDF 页序与引文，无需百炼密钥。审查时参阅[模型相关改动的审查规则](docs/agents/model-review.md)。

```powershell
uv sync --locked --python 3.12
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy
.venv\Scripts\ruff check backend
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

浏览器测试建立隔离数据库并使用明确的 synthetic 合成账号，不读写试用业务数据库。账号审计通过受平台管理权保护的 `/api/account-audit` 查询最近 100 条，仅涉及账号事件；完整审计查询界面在任务 20。

测试默认使用 Playwright 安装的 Chromium。如本机已安装 Google Chrome，也可在运行测试前设置 `$env:AQP_BROWSER = 'chrome'`，此时无需另行下载 Chromium。

### 权限回归

GitHub Actions 在推送和 PR 时用 Windows 运行权限回归，以匹配浏览器测试的现有启动路径。CI 使用 Windows runner 自带的 Chrome。本地完成上面的依赖安装后，从仓库根目录运行与改动对应的命令。

| 改动 | 测试文件与覆盖范围 | PowerShell 命令 |
| --- | --- | --- |
| 评分与导出 | [test_evaluation.py](backend/tests/test_evaluation.py) 验证撤销来源权限后，评分历史、详情、仪表盘和导出遵循当前授权。 | `.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_evaluation.py` |
| 成果列表与汇总 | [test_research_outputs.py](backend/tests/test_research_outputs.py) 和 [test_other_outputs.py](backend/tests/test_other_outputs.py) 覆盖科研论文、专利、获奖、会议及跨专业撤权后的统计。 | `.\.venv\Scripts\python.exe -m pytest -q backend/tests/test_research_outputs.py backend/tests/test_other_outputs.py` |
| 页面刷新与迟到响应 | [partial-access.spec.ts](frontend/tests/partial-access.spec.ts) 验证部分撤权、保留仍有权限的数据及迟到响应，[evaluation.spec.ts](frontend/tests/evaluation.spec.ts) 验证评分页面和导出。 | `npm --prefix frontend run test:e2e -- partial-access.spec.ts evaluation.spec.ts` |
| 首页 Agent 权限与证据 | [agent-scope.spec.ts](frontend/tests/agent-scope.spec.ts) 验证可见学生人数、同名学生定位、日期更正，以及选题撤权后四类成果来源仍可核对。 | `npm --prefix frontend run test:e2e -- agent-scope.spec.ts` |

开发前端可在 frontend 执行 `npm run dev`，并在另一个终端执行启动脚本。Vite 将 API 代理到本机 8000 端口。退出删除服务端会话；停用及角色改变撤销该账号所有会话。登录有限次尝试保护，超限后需等待五分钟。模型默认禁用；Agent查询界面已覆盖学生培养与论文解释的只读工具边界，未配置获准模型时明确显示未启用，不用模拟回答冒充真实结果。真实模型效果验收仍待获准服务。

本机数据库与附件成套备份、隔离恢复及任务恢复：[维护说明](docs/backup-restore.md)。
