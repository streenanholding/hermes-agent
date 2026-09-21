# Oracle Health / Cerner

- **Vendor:** Oracle
- **Deployment:** Cloud.
- **Status:** LIVE PATH
- **Priority:** 3 — strongest legal position to connect without a partnership
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Register at code-console.cerner.com on the free tier and work the sandbox.

## Why it matters
Second-largest health system EHR. Notable because Oracle states in writing that we may connect without joining any partner programme — the clearest such statement from any vendor researched.

## What they require
- CONFIRMED — 'Developers choosing to forgo the validation process may connect to and access API resources but will not have access to value-added services.' No partnership required.
- CONFIRMED — self-serve registration at code-console.cerner.com. Accept terms, review docs, attest to the CARIN Alliance Code of Conduct, register, sandbox test.
- CONFIRMED — provider/system apps additionally need a gap analysis document and a working demo.
- CONFIRMED — FHIR R4 (DSTU2 deprecated and being retired) plus proprietary Millennium APIs.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| FHIR API resources for developers | Free | n/a | CONFIRMED |
| Direct-to-consumer apps | No connection or usage fees — stated in writing | n/a | CONFIRMED |
| Oracle PartnerNetwork membership (optional) | $500/yr | Us | CONFIRMED |
| Millennium Platform Environment Access (optional) | $5,000/yr | Us | CONFIRMED |
| PRACTICE-SIDE: Single-Patient API subscription | $15,000–$30,000/yr by record volume | The practice | CONFIRMED |
| PRACTICE-SIDE: Bulk Data API subscription | $7,000–$28,000/yr by record volume | The practice | CONFIRMED |
| PRACTICE-SIDE: one-time setup | $10,000 (one prod + one non-prod environment) | The practice | CONFIRMED |
| PRACTICE-SIDE: shared / CommunityWorks / Continuum ASP | $1,500–$3,000/yr (discounted) | The practice | CONFIRMED |

## Contacts (published only — nothing invented)
- **Developer console (self-serve registration):** https://code-console.cerner.com
- **API documentation:** https://docs.oracle.com/en/industries/health/millennium-platform-apis/
- **API access and fees:** https://www.oracle.com/health/developer/api/
- **Certified health IT fee schedule:** https://www.oracle.com/health/regulatory/certified-health-it/
- **Developer forums:** https://forums.oracle.com/ords/apexds/domain/open-developer-experience
- **Developer email or phone:** NOT PUBLISHED — use the forums or an Oracle Health sales rep.

## The play
Free for us, expensive for the practice. That inversion is the whole strategy here.

QUALIFY THE PRACTICE'S EXISTING SUBSCRIPTION BEFORE INVESTING A DAY. If a Cerner practice has not already bought the API subscription, our request triggers a $7,000–$30,000 annual cost FOR THEM, plus $10,000 one-time setup. That is a deal-killer for anyone small, and it will sour the relationship if we discover it late. Add one qualifying question to the sales script: 'do you already have the Oracle Health API subscription enabled?' Target sites that already pay it.

THE DTC FEE WAIVER IS IN WRITING. Oracle states direct-to-consumer applications 'will not be charged connection or usage-based fees.' Our patient-facing Magic Link flow may legitimately qualify. That is worth a specific conversation — not a stretch of the definition, but a real question about how our patient-facing component is classified.

Register on the free tier now regardless. It costs nothing, it proves the integration, and it means we are ready the day a Cerner site asks.

## Action steps
1. [ ] Register at code-console.cerner.com on the free tier and work the sandbox.  _(Claude)_
2. [ ] Add an API-subscription qualifying question to the sales script for any Cerner prospect.  _(Rick + Nancy)_
3. [ ] Ask Oracle whether our patient-facing Magic Link component qualifies for the direct-to-consumer fee waiver.  _(Rick)_

## Open questions
- [ ] Does our patient-facing disclosure and consent flow qualify as a direct-to-consumer application for the fee waiver?
- [ ] What is the realistic timeline from registration to a first live client connection?
- [ ] Does the practice-side subscription cover all third-party apps, or is it per-app?

## Log
- 2026-09-20 — seeded.

## Sources
- https://www.oracle.com/health/developer/api/
- https://www.oracle.com/health/regulatory/certified-health-it/
- https://docs.oracle.com/en/industries/health/millennium-platform-apis/
- https://www.oracle.com/a/ocom/docs/industries/healthcare/cerner-certified-health-it-transparency-and-disclosure.pdf
