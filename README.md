# AQP-PGS 学院试用版

当前已实现任务 01～02：本机浏览器访问、个人账号、角色兼任、账号停用、会话、范围授权和脱敏验证。平台管理员不会自动获得学生数据权限；真实学生档案导入由任务 03 继续实现。

登录后进入“授权与脱敏验证”：平台管理员选择账号，按数据类别、操作、学院与专业添加或撤销授权；专业留空表示该学院全部专业。维护、查看、分析、身份展示、导出、原始下载、通过规则、标签、候选规则启用及复核分别配置。下方按钮以当前账号查询三个明确标注的合成样例，演示范围隔离与身份隐藏，不写入真实学生档案。授权更改带版本冲突检查和幂等标识，并记录变更前后内容；后续请求直接读取当前授权。

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

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy
.venv\Scripts\ruff check backend
cd frontend
npm run build
npx playwright install chromium
npm run test:e2e
```

浏览器测试建立隔离数据库并使用明确的 synthetic 合成账号，不读写试用业务数据库。账号审计通过受平台管理权保护的 `/api/account-audit` 查询最近 100 条，仅涉及账号事件；完整审计查询界面在任务 20。

测试默认使用 Playwright 安装的 Chromium。如本机已安装 Google Chrome，也可在运行测试前设置 `$env:AQP_BROWSER = 'chrome'`，此时无需另行下载 Chromium。

开发前端可在 frontend 执行 `npm run dev`，并在另一个终端执行启动脚本。Vite 将 API 代理到本机 8000 端口。退出删除服务端会话；停用及角色改变撤销该账号所有会话。登录有限次尝试保护，超限后需等待五分钟。模型默认禁用；Agent查询界面已实现只读工具边界，未配置获准模型时明确显示未启用，不用模拟回答冒充真实结果。真实模型效果验收仍待获准服务。

本机数据库与附件成套备份、隔离恢复及任务恢复：[维护说明](docs/backup-restore.md)。
