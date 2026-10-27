TWINPANEL_MANUAL_CUTOVER_ELIGIBILITY_V289

This file intentionally documents the regression contract covered by
`manual_cutover_eligibility_v289_smoke.py`:

- Smart Auto qualification keeps the 60-second stability requirement.
- Manual cutover eligibility does not depend on Smart Auto stability history.
- Manual cutover still requires the candidate to be installed/enabled/online
  and not policy-blocked.
- Every explicit manual cutover still runs a fresh full dataplane probe,
  requires fresh healthy reports from both peer Agents, and rolls authority
  back on failure.
- The UI exposes one manual-control surface for every logical tunnel and uses
  `manual_selectable` for button readiness while keeping `qualified/selectable`
  as the backward-compatible Auto qualification signal.
