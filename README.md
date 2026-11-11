# AQP-PGS 学院试用版

当前实现任务 01：本机浏览器访问、个人账号、三类角色兼任、账号停用、服务端会话和账号审计。学生数据与细分授权在后续任务实现，平台管理员不会自动获得学生数据权限。

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

开发前端可在 frontend 执行 `npm run dev`，并在另一个终端执行启动脚本。Vite 将 API 代理到本机 8000 端口。退出删除服务端会话；停用及角色改变撤销该账号所有会话。登录有限次尝试保护，超限后需等待五分钟。模型和外部服务尚未接入。
