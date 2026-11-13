# Snapshot access boundary correction

Reports and Agent now reuse the evaluation snapshot loader. Current basic, evaluation and metric source view/identity/analyze grants and current student scope are checked before returning saved scores. Student report export additionally checks basic/evaluation and only the actual rule metric source export grants. Source changes preserve saved snapshots; reports omit stale totals, Agent snapshot explanations expose stale status, and score correlations exclude stale values with an explicit exclusion count and notice.

Tests use synthetic records and a model runner substitute through public HTTP endpoints. They do not constitute real model or real student data acceptance. Existing tests were extended after implementation; this work does not claim a test-first cycle.

The existing evaluation denial audit commits its connection before raising. This patch preserves that audit behavior. Newly shared report/Agent paths perform reads before authorization; snapshot export performs no business writes before denial; scoring inserts its snapshot only after input authorization. Changing denial transaction ownership is outside this patch.

Validation: related Agent/evaluation tests 19 passed; ruff passed; mypy passed for 31 source files. Final full regression: 145 tests passed in 137.66 seconds. Report source grant/export focused test: 1 passed. After the final stale-notice wording adjustment, the Agent snapshot public API test passed (1 test); ruff passed. Source invalidation is simulated by direct database setup in these tests; public source-revision acceptance remains separate.
