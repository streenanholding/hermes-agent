# Veradigm / Allscripts  +  Practice Fusion

- **Vendor:** Veradigm (Practice Fusion is a Veradigm company)
- **Deployment:** Cloud.
- **Status:** GATED
- **Priority:** 3 — honest tiering, and one confirmed email that covers both
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Download the Certified EHR API Fees spreadsheet from practicefusion.com/fhir. Zero cost, immediate.

## Why it matters
Covers TouchWorks, Professional EHR and Practice Fusion. Practice Fusion in particular serves small independent practices, which is the likeliest early-adopter profile for us.

## What they require
- CONFIRMED — tiered. 'Open' tier is FREE: 'Free to build and deploy by anyone' with FHIR-enabled APIs, via click-through agreement, no negotiated contract. 'Integrator' tier is PAID across five levels (Bronze, Silver, Gold, Platinum, Platinum Plus) and is required for the proprietary Unity API.
- CONFIRMED and unusually honest — Veradigm states plainly that FHIR is READ-ONLY and anything bidirectional requires Unity, i.e. the paid tier. Our write-back therefore requires a paid Integrator tier.
- CONFIRMED — production apps require Veradigm Connect review and approval regardless of tier.
- CONFIRMED (Practice Fusion) — separate PDS API Partner Registration Form plus Terms of Service, then a PDS API Partner Application with technical specifications. Practices then control data sharing in the EHR.
- CONFIRMED (Practice Fusion) — FHIR R4 with US Core v6.1.0, notably more current than most peers. Separate Labs, Imaging and BILLING APIs exist — the Billing API is the one relevant to patient balances.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Veradigm Open tier | $0 | n/a | CONFIRMED |
| Veradigm Integrator tiers | Monthly, or 10% discount if purchased annually — amounts not published | Us | NOT CONFIRMED — ask |
| Practice Fusion certified EHR API fees | A fee spreadsheet dated May 2024 is published on their FHIR page | Unknown | NOT CONFIRMED — download the file |

## Contacts (published only — nothing invented)
- **Veradigm developer portal:** https://developer.veradigm.com/
- **Programme overview and tiers:** https://developer.veradigm.com/Home/LearnMore
- **FHIR process overview:** https://developer.veradigm.com/Fhir/ProcessOverview
- **Email — covers Veradigm AND Practice Fusion:** VeradigmConnect@veradigm.com
- **Practice Fusion FHIR programme:** https://www.practicefusion.com/fhir/
- **Practice Fusion registration:** https://pfpds.practicefusion.com/s/Registration
- **Practice Fusion phone:** (415) 993-4977

## The play
Two immediate, zero-cost actions here that are among the best-value moves in this entire workbook.

FIRST — DOWNLOAD PRACTICE FUSION'S PUBLISHED FEE SPREADSHEET. They publish a 'Certified EHR API Fees' Excel file dated May 2024 in the Resources section of practicefusion.com/fhir. It is an actual price sheet we can obtain today without talking to anyone. Almost no vendor on this list publishes one. Get it before any call so we walk in already knowing their numbers.

SECOND — EMAIL VeradigmConnect@veradigm.com IN WEEK ONE. It is a confirmed, monitored address and it covers both Veradigm and Practice Fusion. Ask for Bronze and Silver Integrator pricing. Their pricing page was erroring when we researched, so the email is the only route.

USE THE FREE OPEN TIER TO SCOPE PRECISELY. Because Veradigm is unusually straight about what is read-only and what is not, we can build the read layer on the free tier and know exactly what the paid tier has to buy. That makes the eventual negotiation concrete — we will be asking for one specific capability, not open-ended access, which is always a cheaper conversation.

## Action steps
1. [ ] Download the Certified EHR API Fees spreadsheet from practicefusion.com/fhir. Zero cost, immediate.  _(Claude)_
2. [ ] Email VeradigmConnect@veradigm.com for Bronze and Silver Integrator tier pricing.  _(Rick)_
3. [ ] Register on the free Open tier and build the read layer.  _(Claude)_
4. [ ] Submit the Practice Fusion PDS API Partner Registration separately.  _(Claude)_

## Open questions
- [ ] What do the Bronze and Silver Integrator tiers cost per month?
- [ ] Which specific Unity capabilities do we need for a single note write-back, and what is the minimum tier that includes them?
- [ ] Does the Practice Fusion Billing API expose patient balances, and what tier does it require?
- [ ] How long does Veradigm Connect production review typically take?

## Log
- 2026-09-20 — seeded.

## Sources
- https://developer.veradigm.com/Home/LearnMore
- https://developer.veradigm.com/Fhir/ProcessOverview
- https://www.practicefusion.com/fhir/
- https://www.practicefusion.com/fhir/get-started/
