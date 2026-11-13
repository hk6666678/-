# Final source-fix verification (2026-11-13)

已确认模拟完整版范围验证完成，两轴最终复审可合，已合入根 integration/aqp-trial：1479b0e；根最终交接提交bb76b9e。最终根回归145 pytest、mypy31、Ruff、build、Chrome23/23全部通过。已包含来源授权P1修复；本节取代下方历史WIP状态。真实业务验收仍待输入。

- 最终小样本扩展：data/full10-final-small/full-platform-report.json，passed，2.021s，15项记录；恢复 data/full10-final-small-restored/report.json，passed，2.881s，25项记录。
- 最终全量基线克隆扩展：data/full10-final-scale/full-platform-report.json，passed，1.807s，15项记录；恢复 data/full10-final-scale-restored/report.json，passed，28.942s，25项记录。复用既有干净1000/30000/2000/2000/100基线，未重导。新增合成量见历史章节，时长为本机观察不是性能承诺。
- Chrome 157.0.8103.39；OS/CPU/Python见扩展JSON，完整HTTP/sqlite环境见基线JSON。全部附件文件hash和PDF原件hash一致；三级Excel按表名与单元格内容比较，仅排除生成时间行；JSON仅排除顶层generated_at。
- 独立工具审查两项已修：启动先拒非空AQP_ATTACHMENTS，公开CLI修前return0且生成输出，修后在读取不存在manifest之前拒绝、无输出目录/服务；三个报表导出都断言200并openpyxl解析非空，不再仅记录状态。
- 默认Agent真实HTTP503，未启用模型；独立identity/export/download、A/B、导师兼任管理员绑定/撤绑矩阵通过。来源P1另有根145pytest/19专项与独立审查证据；本工具最终恢复覆盖修复后评分/报告摘要。
- Ruff通过；最终合并1479b0e已由根merger完成145pytest（133.75秒）、mypy31、Ruff、build、Chrome23/23（46.7秒）回归。所有本工具HTTP/Chrome服务已结束；无真实data修改，无push。

任务10四条AC的模拟范围均有公开HTTP、版本来源、权限、浏览器和静态/回归证据；原案外网抓取、训练、因果反事实、PDFWord排版、真实专家模型及正式部署验收不在本轮完成声明。下方保留失败历史与当时缺口，不覆盖最终状态。

---

# Full10 simulation acceptance checkpoint (historical)

Status: WIP, pending source-authority P1 integration and final rerun/review. Synthetic evidence only; not real business acceptance. Local commits only, no push.

## Reproduction

From repository root in PowerShell, set `$env:PYTHONPATH='backend'`.

1. `uv run python backend/tests/trial_scale.py --output data/<new-baseline> --small` (omit --small for existing 1000 students / 30000 courses / 2000 topic / 2000 midterm / 100 paper baseline).
2. `uv run python backend/tests/full_platform_validation.py --manifest data/<baseline>/report.json --output data/<new-extension>`.
3. Build frontend (`npm --prefix frontend run build`), then `uv run python backend/tests/trial_restore.py --manifest data/<extension>/report.json --output data/<new-recovery>`.

Each extension copies the stopped baseline with SQLite backup plus attachments into a new directory. Never reuse a populated output directory. Baseline remains untouched. HTTP probes use actual loopback uvicorn/httpx, including five independent account requests; no TestClient concurrency claims.

## Actual evidence so far

- `data/full10-clean-small-ext1` and `ext2`: repeated isolated extension passed. Mentor+platform_admin with broad A/B grants sees only bound A (1), B report 403; unbind yields zero and A report 403.
- `data/full10-clean-small-restored-v2/report.json`: CLI backup and restore plus installed Chrome passed, including Excel semantic content comparisons.
- `data/full10-clean-scale/report.json`: clean full baseline passed in 70.487 seconds; five-account analysis write stage 41.737 seconds. This is an observed local duration, not a capacity/SLA promise.
- `data/full10-clean-scale-ext/full-platform-report.json`: extension passed 13 checks. Adds one B student, four output records (one later corrected into a two-college patent), two external assessments, one mentor/group/relation, one simulation rule/snapshot and a citation date snapshot. Baseline original counts stay separate from these additions.
- `data/full10-clean-scale-restored/report.json`: recovery passed in 32.153 seconds, 25 recorded checks. Four-output lists, external assessments, directories, relations, evaluation and three report JSON responses match by SHA256 after excluding only top-level generated_at. Three report workbook hashes compare worksheet names and cell values, excluding generated_at rows; PDF download matches raw bytes. Old session returns 401, fresh Chrome login and source/PDF/review pages passed.
- `data/full10-small-matrix-v2/full-platform-report.json`: identity revocation returns null identity fields and Excel contains neither planted number nor name; export-only revocation returns 403 while report remains 200; paper download-only revocation returns 403 while report remains 200. Each temporary operation matrix restores grants in finally.

## Failure history and limitations

Earlier attempts remain on disk: missing PYTHONPATH; B student beyond 200-page cap; mistaken assumption that redacted fields are absent rather than null; comparison failures from report/export generated_at; an interrupted non-isolated extension polluted grants. These are tool defects corrected with explicit pagination, public-contract assertions, documented semantic canonicalization and isolated baseline cloning. They are not counted as passing runs. A failed clone remains for diagnosis; no original data is deleted.

Before source P1 merge, report evaluation still reused stored summary without rechecking evidence authority; final acceptance must rerun after the root fixes that issue. No claim of final task10 completion yet. Remaining: source view/analyze revocation across report/Agent, browser redaction matrix, explicit Agent default-disabled assertion in this tool, source file hashes, full regression and independent review. Runtime environment is recorded in baseline and extension JSON (OS/Python/CPU/sqlite/httpx/uvicorn); Chrome engine is actual installed Chrome, exact version still to capture.

## Acceptance mapping

| Task10 criterion | Evidence / remaining |
|---|---|
| Data, public API and UI | Four templates preview/confirm, citations, assessment workbook import, mentor relation, simulation rule and snapshot, three reports; recovery Chrome checks existing UI; broader browser suite pending final rerun |
| Current authority, identity, versions and audit | A/B isolation and mentor binding; independent identity/export/download matrix; patent v2 correction marks old score stale; source-authority P1 and audit full regression pending |
| API/browser synthetic verification vs business | Real HTTP and Chrome evidence above; only synthetic students, papers and simulation weights |
| Static build/regression/local delivery | Ruff and TS/Vite build passed during slices; full pytest/mypy/e2e and independent review pending; no push |

Real school data, expert-approved official weights, authorized model semantic quality, formal deployment/HTTPS and production load remain later acceptance. No configured model service is enabled and no real data or paper content was sent to a model. Correlation/regression are descriptive research tools, not causal claims. All test services stop before backup; archived and restored attachments stay isolated under the synthetic output directory.
