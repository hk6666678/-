# Full10 simulation acceptance checkpoint

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
