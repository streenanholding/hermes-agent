# {{Vendor or payer name}}

<!-- Copy to /opt/data/trackers/vendors/<slug>.md. Keep every `- **Field:**` line:
     stale_check.py and tracker_rollup.py read them. Anything not confirmed
     from a source is written NOT CONFIRMED. No credentials, ever. -->

- **Type:** {{clearinghouse | dental-benefits vendor | direct payer connection}}
- **Status:** {{LIVE | IN MOTION | GATED | BLOCKED | UNKNOWN | NOT PURSUING}}
- **Priority:** {{1-5}} — {{one-line why}}
- **Owner:** {{Rick | Nancy | Agent 2}}
- **Last movement:** {{YYYY-MM-DD}}
- **Last action:** {{YYYY-MM-DD}} — {{what happened}}
- **Next action:** {{what}} ({{who}}, by {{YYYY-MM-DD}})

## Why it matters
{{One paragraph: what this connection unlocks for PayVerified.}}

## What they require
- {{CONFIRMED | NOT CONFIRMED}} — {{requirement}} [S1]

## Transactions covered
| Transaction | Supported? | Source |
|---|---|---|
| 270/271 eligibility | {{yes/no/NOT CONFIRMED}} | [S1] |
| 276/277 claim status | {{}} | |
| 835 ERA | {{}} | |
| 837D/837P claims | {{}} | |
| Enrollment API (ERA/EFT) | {{}} | |

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| {{item}} | {{amount or "not published, must ask"}} | {{}} | {{CONFIRMED [S1] / NOT CONFIRMED}} |

## Contacts (published only, nothing invented)
- {{role}}: {{published email / page URL}}

## Open questions
- [ ] {{question}}

## Log
- {{YYYY-MM-DD}} — {{event}}

## Sources
- [S1] {{https://...}}
