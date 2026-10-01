# {{Practice name}} — payer enrollment

<!-- Copy to /opt/data/trackers/practices/<slug>.md. PROVIDER FACTS ONLY:
     NPI, TIN, legal/DBA name, practice address, business contacts.
     NEVER patient data. NEVER bank, routing or account numbers: the EFT bank
     section is always completed by the practice directly with the payer. -->

- **Status:** {{IN MOTION | BLOCKED | ENROLLED}}
- **Owner:** {{Rick | Nancy}}
- **Last movement:** {{YYYY-MM-DD}}
- **Last action:** {{YYYY-MM-DD}} — {{what happened}}
- **Next action:** {{what}} ({{who}}, by {{YYYY-MM-DD}})
- **Clearinghouse:** {{name}} (tracker: vendors/{{slug}}.md)

## Provider facts
- Legal name: {{}} [S1]
- DBA: {{}} [S1]
- Type 2 (group) NPI: {{10 digits}} [S1]
- Rendering NPIs: {{list or "see practice roster"}} [S1]
- TIN/EIN: {{NN-NNNNNNN}} [S1]
- Practice address: {{}} [S1]
- Business contact for enrollment: {{name, role, business email}} [S1]
- State(s): {{}}

## Enrollment path
Clearinghouse enrollment API first; payer portal or paper only where the API doesn't cover it.

| Payer | ERA (835) | EFT | Eligibility (270/271) | Route | Status | Source |
|---|---|---|---|---|---|---|
| {{payer}} | {{needed/done}} | {{needed/done}} | {{}} | {{clearinghouse API / payer portal (Rick) / paper}} | {{}} | [S1] |

### Government programs
- Medicare (HETS eligibility): {{applies? path}} [S1]
- State Medicaid: {{state, program}} [S1]
- Medicaid MCOs: {{list}} [S1]

## Blockers and open questions
- [ ] {{}}

## Log
- {{YYYY-MM-DD}} — {{event}}

## Sources
- [S1] {{https://... or "practice intake form, received YYYY-MM-DD"}}
