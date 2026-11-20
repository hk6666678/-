# 任务22B：本机合成规模与HTTP并发实测

2026-11-12；结论：下述合成规模流程通过；首次五账号并发暴露SQLite写锁超时，修复后最小回放及全量重跑通过。本记录不代表全部AC或真实业务验收通过。

## 环境与方法

Windows 10 build 19045 AMD64；Intel64 Family 6 Model 183 Stepping 1 GenuineIntel；28逻辑CPU。Python 3.12.12、SQLite 3.50.4、httpx 0.28.1、uvicorn 0.54.0。硬件型号和内存容量未另行采集；同机其他测试活动可能影响耗时。不设固定性能承诺。

`backend/tests/trial_scale.py`启动实际127.0.0.1 uvicorn服务，httpx通过网络登录、读取四类当前模板、生成标注为合成的文件、预览并使用各自确认路由导入。学生标识来自API查询，论文使用可解析合成文本PDF。每项数量来自学生列表、课程／选题／中期分析及论文列表与worker结果查询断言，未把生成常量作为实测结果。五个独立账号先各自登录，再用barrier同时提交课程分析；每个分析需返回30000考核记录和不同的分析快照ID。

## 实际结果

先运行小切片：10学生、30课程、各20选题／中期、2篇PDF；五账号并发成功，总计2.223秒。早期脚本调试出现本机代理、控制台编码和分页参数问题，失败产物保留在data/trial-22b-small至small-3；最终小切片为small-4。

完整重跑产物位于`data/trial-22b-final/`，总计70.935秒，报告status=passed、failures=[]、服务已退出。

| API查询或处理结果 | 实际数量 |
| --- | ---: |
| 学生档案 | 1000 |
| 课程考核 | 30000 |
| 选题考核 | 2000 |
| 中期考核 | 2000 |
| 论文列表／worker成功解析 | 100／100 |

100篇论文逐篇通过证据API确认存在Synthetic text。输入PDF共用同一合成正文，验证的是持久化解析链及容量，不代表真实论文差异或智能语义能力。

| 步骤（含客户端生成文件及往返） | 秒 |
| --- | ---: |
| 基础导入 | 0.940 |
| 三批课程导入 | 12.322 |
| 选题导入 | 1.321 |
| 中期导入 | 1.405 |
| 课程数量分析查询 | 7.746 |
| 选题数量分析查询 | 1.066 |
| 中期数量分析查询 | 0.403 |
| 论文上传、worker、证据查询 | 4.250 |
| 五账号同时分析写入 | 36.849 |

## 并发缺陷与回归

首次全量导入数量及论文检查均通过，但五账号并发未通过。第二次保留的全量红灯data/trial-22b-full-2中：2/5 HTTP200，3/5 HTTP500，失败请求约10.92秒；服务端异常为`analysis.py analyze`在`BEGIN IMMEDIATE`抛出`sqlite3.OperationalError: database is locked`。完整栈保留于data/trial-22b-full-2-console.log。

独立最小回放`trial_scale_concurrency.py`直接重用此合成数据库，省略导入，再次得到3/5失败（HTTP500，约10.94秒），证据为data/trial-22b-concurrency-red.json及.log。

原因是课程分析持有写事务计算并保存一致的分析快照，单个30000条分析实测约7～8秒，五请求顺序排队超过原连接10秒等待。最小修复仅为分析端点设置`PRAGMA busy_timeout=60000`，保留原事务及一致性检查。选择60秒依据是五次约7～8秒分析约需35～40秒；修复后最小回放实际最慢41.048秒（总43.970秒，期间同机运行其他测试）。此值是有界等待，不是吞吐提升或普适容量保证；更多账号、更慢机器或更大数据仍可能达到超时，后续需另评计算与写事务分离方案。

修复后最小回放5/5 HTTP200、0失败、各30000记录、五个不同快照ID（8～12）。原全量脚本也重新生成数据并通过，五账号结果如下：

| 账号序号 | HTTP | 秒 | 考核数 | 快照ID |
| --- | ---: | ---: | ---: | ---: |
| 0 | 200 | 22.049 | 30000 | 6 |
| 1 | 200 | 7.468 | 30000 | 4 |
| 2 | 200 | 14.815 | 30000 | 5 |
| 3 | 200 | 29.490 | 30000 | 7 |
| 4 | 200 | 36.842 | 30000 | 8 |

五请求失败率0/5，仅代表此轮；SQLite写入仍排队。本轮验证分析创建与数量一致、快照无重复；其他功能的并发更正、重复导入和后台任务恢复应结合各自测试及22C记录评估。

## 重现与恢复接口

在仓库根目录PowerShell执行（使用已安装的Python3.12环境替换下列路径）：

```powershell
$env:PYTHONPATH='backend'
$env:PYTHONUTF8='1'
D:/AQP-PGS/.venv/Scripts/python.exe backend/tests/trial_scale.py --small --output data/new-small
D:/AQP-PGS/.venv/Scripts/python.exe backend/tests/trial_scale.py --output data/new-full
D:/AQP-PGS/.venv/Scripts/python.exe backend/tests/trial_scale_concurrency.py --database data/new-full/aqp.sqlite3 --report data/new-concurrency.json
```

输出目录必须不存在，避免覆盖验收证据。全部data/产物为合成并本机保留，不提交数据库、附件或完整导入行到Git。完整最终目录含aqp.sqlite3、attachments/、生成模板与输入、synthetic-text.pdf、report.json；报告给出database、attachments、synthetic_account、analysis_ids、paper_ids及实测数量。恢复探针可使用上述路径；账号和口令均为脚本中明确标注的合成测试值。22B未创建比较／候选／人工复核链，需22C另行补齐并验证恢复。

补充检查：test_analysis.py与test_trial_samples.py共5 passed（21.18秒）；本次三个代码文件Ruff通过。完整项目类型、构建与测试结果由任务22总验收汇总，本记录不替代这些检查。未使用真实学生数据、外部模型或专家规则；规模验证未启用Agent，不代表真实模型验收。
