# Full07 WIP checkpoint

Branch codex/full-07; base 0f4694c. Local commits only; no push.

Implemented simulation-only immutable draft/activation rules, separately authorized activation, rule listing, snapshot scoring and read with current student/source/mentor permission checks, digest/stale, explicit weights and min/max, missing suppresses total. Six supported current backend metrics; course unknown causes missing; latest citation uses date then version. Migrations260 rules/261 snapshots support old applied260 and already-created snapshot table. Stable weighting scales by max weight before summing; snapshots JSON disallows NaN.

Verification: six public API tests, local ruff and mypy; frontend build; Chrome evaluation.spec.ts one pass covering draft to independent activation. Actual screenshot artifacts/full07-simulation.png viewed locally; root independently reviewed earlier screenshot. Screenshot after local checkbox/textarea fix reviewed locally. This is synthetic workflow verification, not business acceptance.

Remaining: authorized student research-id chooser and snapshot list chooser (currently internal-id inputs); real official/business rule configuration (currently simulation only); export independent authorization and endpoint; radar/growth series with real snapshots and missing years; richer source department/raw record evidence; more broad regression/full Chrome and responsive proof. Do not merge or claim full07 complete. Current UI score path not Chrome-covered. Do not describe scores as formal talent recognition.

Last official account quota read: short remaining11%, weekly33%; shared account not real-time guarantee. No background app processes intentionally kept running; Playwright webServer closed after run. artifacts screenshot is untracked local evidence.
