# 本机成套备份与隔离恢复

维护命令：在项目根目录的 PowerShell 设置 `$env:PYTHONPATH="backend"`，使用 `uv run python -m aqp.backup`。需要本机文件访问权；该离线维护工具不提供绕过网页授权的公共接口。归档含业务个人数据、账号密码哈希与原始论文，应按生产数据权限保管。工具不采集环境变量、API密钥、配置文件或明文密码；账号可使用原密码重新登录。

## 备份

1. 关闭 Start-Aqp.ps1 启动的服务，停止所有独立 API、paper_worker 及其他后台 worker，确保整个备份期间无人启动服务或修改数据库、附件。`--services-stopped` 是维护人员对此前置条件的显式确认，工具不能发现所有外部进程；在线备份不受支持。
2. 明确实际 AQP_DB 与 AQP_ATTACHMENTS 路径（默认附件为数据库同级 attachments），目录必须存在。执行：

```powershell
uv run python -m aqp.backup create --db D:\AQP-data\aqp.sqlite3 --attachments D:\AQP-data\attachments --archive D:\AQP-backups\trial-20261112.zip --services-stopped
```

3. 成功后再启动服务。命令使用 SQLite backup API 获取包含已提交 WAL 数据的独立快照，再收集整个附件目录；停服务保证两者在同一业务状态。数据库完整性、外键、每条附件及论文版本的长度/hash均需通过，不能以复制活跃 SQLite 主文件替代。

归档只含 aqp.sqlite3、attachments/ 文件及 manifest.json。清单覆盖所有文件长度和 SHA-256；数据库完整保留来源、历史版本、分析结果、复核与审计联系。SHA-256用于损坏检查，不是来源签名，归档来源仍须可信。

## 恢复及验证

```powershell
uv run python -m aqp.backup restore --archive D:\AQP-backups\trial-20261112.zip --target D:\AQP-recovery\trial-check
```

目标父目录需存在，目标目录必须不存在；不能默认覆盖生产数据库或附件目录。命令拒绝重复ZIP条目、路径穿越、符号链接/目录联接、未列入清单文件和损坏内容。先在专属临时目录完成验证，再发布整个目标目录。失败不发布恢复目录；进程被强制中断可能遗留 `.aqp-maintenance-*`，应停服务、检查内容后由维护人员清理；重试使用原归档与不存在的目标即可。创建归档中断留下的不完整 ZIP 不可当作成功备份，应另用新文件名重试。

恢复删除所有旧 sessions，保留账号和密码哈希，要求重新登录；审计记录 maintenance.restore。processing paper_jobs 重置为 queued 并清除旧token，版本ID保持不变；使用现有worker原子领取、token围栏及一次事务发布结果，不重排成功任务。仅在隔离恢复库启动 worker，不能让原库 worker 连接恢复库。

将 AQP_DB 指向目标 aqp.sqlite3，AQP_ATTACHMENTS 指向目标 attachments，再启动隔离API/前端。重新登录后在浏览器核验统一学生档案、原始来源与附件历史、论文下载和页序证据；核验已存在分析/复核版本关联。旧cookie必须401。仅验证完成后再由部署维护流程切换服务路径。恢复中保留所有业务表，不执行自动迁移或删除历史版本；使用匹配版本程序恢复后再按部署流程迁移。

任务21自动验收从真实CLI进程及公开HTTP接口运行合成备份/恢复、拒绝已有目录与恶意ZIP、旧session失效及原账号重新登录。最终全功能浏览器数据链路由任务22在所有功能集成后验收，不将合成测试当作真实模型验收。
