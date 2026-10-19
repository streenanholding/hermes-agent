# Tracker templates

- `vendor.md` — one per clearinghouse, dental-benefits vendor or direct payer
  connection, at `/opt/data/trackers/vendors/<slug>.md`.
- `payer-enrollment.md` — one per practice, at
  `/opt/data/trackers/practices/<slug>.md`.

Slugs are lowercase-hyphenated (`stedi`, `smith-family-dental`).
`tracker_rollup.py` rewrites `/opt/data/trackers/README.md` as the live index.

Status keys: LIVE · IN MOTION · GATED · BLOCKED · UNKNOWN · NOT PURSUING
(vendors); IN MOTION · BLOCKED · ENROLLED (practices). LIVE, ENROLLED and
NOT PURSUING are skipped by the stale check.

Update `Last movement` only when something actually moved: a reply, a
submission, a decision. Re-reading a tracker is not movement.
