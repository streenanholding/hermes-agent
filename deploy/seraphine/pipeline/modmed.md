# ModMed / Modernizing Medicine

- **Vendor:** Modernizing Medicine
- **Deployment:** Cloud.
- **Status:** UNKNOWN
- **Priority:** 2 — highest strategic fit of any medical system here
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Call (561) 880-2998 and ask for pricing on both the certified and the proprietary EMA API.

## Why it matters
ModMed is concentrated in dermatology, ophthalmology, plastics, orthopaedics and GI — the elective and cash-pay specialties where patient financing is actually used. This is the closest fit to our product of any medical EMR on the list.

## What they require
- CONFIRMED — three API tiers. Certified FHIR API (R4, bulk NDJSON export, SMART on FHIR). EMA Proprietary API — customized FHIR R4 with CREATE, READ, SEARCH and UPDATE operations. A third proprietary FHIR variant plus HL7 options.
- CONFIRMED — registration via a vendor dashboard supplying app name, launch URL, redirect URL, logo, policy URL, ToS URL; access type (Public or Client-Confidential), PKCE, app type (Patient / Provider / both / Bulk); FHIR 4.0.1; scope selection at patient, user or system level.
- NOT CONFIRMED — whether a signed commercial agreement precedes the proprietary write-capable API.
- NOT CONFIRMED — cost of anything, certified or proprietary. Nothing published.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Everything — certified and proprietary | Not published anywhere | Unknown | NOT CONFIRMED — ask |

## Contacts (published only — nothing invented)
- **Developer portal:** https://portal.api.modmed.com/
- **Getting started:** https://portal.api.modmed.com/docs/getting-started
- **Vendor registration dashboard:** https://fhir-vendor-dashboard.kube.prod.mmicse.com/
- **API Terms of Use:** https://www.modmed.com/api-terms-of-use/
- **Phone:** (561) 880-2998
- **Address:** 4700 Exchange Court Suite 225, Boca Raton FL 33431
- **Email:** NOT RESOLVED — obfuscated on their portal. Must ask by phone.

## The play
The best product-market fit on the medical side, and the lowest engineering cost for the one thing every other vendor makes hard.

THEIR PROPRIETARY API DOES CREATE AND UPDATE, IN FHIR SHAPE. Everywhere else, write-back means a bespoke HL7 interface build or a proprietary SOAP contract. ModMed's proprietary API is FHIR-shaped and documented with CREATE and UPDATE operations — meaning our note write-back is likely achievable with the same code patterns as the read. That is a material saving in build time, and it is the reason to prioritise ModMed above vendors with published pricing.

SPECIALTY CONCENTRATION IS THE COMMERCIAL ARGUMENT. Derm, plastics and ophthalmology run high-ticket elective procedures financed at the point of care — exactly the transaction our disclosures govern. When we call, lead with that: we are not a generic integration request, we are a compliance layer for the financing their customers already do every day.

Because nothing is published, the call IS the research. Make it early — an unknown cost is a planning risk and this one is cheap to remove.

## Action steps
1. [ ] Call (561) 880-2998 and ask for pricing on both the certified and the proprietary EMA API.  _(Rick)_
2. [ ] Register on the vendor dashboard and assess the proprietary API's CREATE/UPDATE for our write-back.  _(Claude)_
3. [ ] If pricing is reasonable, promote ModMed to a top-two medical target on strategic fit.  _(Rick)_

## Open questions
- [ ] What does the certified FHIR API cost, and what does the EMA Proprietary API cost?
- [ ] Is a signed commercial agreement required before accessing the proprietary write-capable API?
- [ ] Does any ModMed API expose patient balance or accounts-receivable data?
- [ ] What is the timeline from vendor registration to production access?

## Log
- 2026-09-20 — seeded.

## Sources
- https://portal.api.modmed.com/
- https://www.modmed.com/api-terms-of-use/
- https://www.modmed.com/wp-content/uploads/2023/01/MMI-Public-Facing-Cert-API-Documentationv2.pdf
