# Full07 WIP checkpoint

Branch codex/full-07; base 0f4694c. Local commits only; no push.

Implemented simulation-only immutable draft/activation rules, separately authorized activation, rule listing, snapshot scoring and read with current student/source/mentor permission checks, digest/stale, explicit weights and min/max, missing suppresses total. Six supported current backend metrics; course unknown causes missing; latest citation uses date then version. Migrations 260 rules / 261 snapshots support old applied 260 and already-created snapshot table. Stable weighting scales by max weight before summing; snapshots JSON disallows NaN.

2026-11-13 second checkpoint (this round): snapshot history listing endpoint re-checks student access and rule scope now, so deactivation or grant changes hide history; snapshot export requires the independent export grant on talent_evaluation plus every involved source category and basic, then re-runs full input permission checks and emits the standard Excel report with audit. UI replaced the internal-id history input with a permission-filtered snapshot chooser, adds an SVG radar (declines to draw below 3 metrics instead of a misleading degenerate line), an honest growth chart over real saved snapshots only (no fabricated years, no extrapolation, same-second snapshots overlap), and an export download button. Evaluation Chrome spec now covers the full loop: unique student import, patent/paper/award imports, 3-metric rule draft, independent activation, two scorings 10.00 then 13.33 after a real second patent, radar/growth visibility, history re-read, xlsx download filename, and a 550px single-column responsive assertion.

Verification this round (HEAD to be confirmed by git log): backend pytest 137 passed (227s), mypy 30 files clean, ruff clean, TS/Vite build passes, full Chrome suite 22/22 twice (36.3s, 36.4s). Two rounds of independent screenshot review of the snapshot card caught label clipping (radar left axis, growth right date); both fixed and re-verified. Synthetic data only; not business acceptance.

Remaining: real official/business rule configuration (simulation mode only by design until business supplies confirmed weights); richer source department/raw-record drill-down in evidence display; full-platform two-axis review and serial integration; broader regression after merge. Do not merge or claim full07 complete. Do not describe scores as formal talent recognition.

Student scoring uses current-authorized /api/students research-id select, optional exact major filter, first-200 and total limitation explicitly shown.

Quota note: this session's host exposes no official get_usage_limits tool, so the official-account percentage cannot be read or guaranteed here; last known reading in the root HANDOFF was short 5% stop (95 used) at the previous stop. All work in this round stayed local with no push.
