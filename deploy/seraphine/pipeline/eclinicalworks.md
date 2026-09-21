# eClinicalWorks

- **Vendor:** eClinicalWorks
- **Deployment:** Cloud.
- **Status:** LIVE PATH
- **Priority:** 2 — biggest free footprint in medical
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Register on the provider developer portal at fhir.eclinicalworks.com/ecwopendev.

## Why it matters
180,000+ physicians. Their certified FHIR APIs are free to third-party developers in writing, and uniquely that includes PROVIDER-facing apps, not just patient-facing ones. That is the widest free door available.

## What they require
- CONFIRMED — 'Certified FHIR APIs are available to third-party application developers and eClinicalWorks customers at no cost at this time.' They commit to 30 days' notice before introducing any fee.
- CONFIRMED — two portals. Provider-facing (SMART on FHIR, bulk/backend) at fhir.eclinicalworks.com/ecwopendev. Patient-facing at connect4.healow.com. We likely need the provider portal for treatment context.
- CONFIRMED — FHIR R4.
- NOT CONFIRMED — whether non-certified capability or write-back requires a commercial agreement. Must ask.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Certified FHIR APIs | Free at this time, 30 days' notice before any change | n/a | CONFIRMED |
| Value-added services | eCW notes they may charge in future | Us | NOT CONFIRMED — none currently |
| Write-back / non-certified capability | Not published | Unknown | NOT CONFIRMED — ask |

## Contacts (published only — nothing invented)
- **Provider-facing developer portal (the one we need):** https://fhir.eclinicalworks.com/ecwopendev/
- **Patient-facing portal:** https://connect4.healow.com/
- **Interoperability overview:** https://www.eclinicalworks.com/products-services/interoperability/
- **Certified EHR technology page (where the free statement lives):** https://www.eclinicalworks.com/resources/certified-ehr-technology/
- **Phone:** 508-836-2700 (sales line — ask for Interoperability / Platform for Open Development)

## The play
Best free footprint in medical, so treat it as a top-two medical target alongside Greenway.

USE THE PROVIDER PORTAL, NOT THE PATIENT ONE. The split matters. Patient-facing gets us demographics; provider-facing gets us treatment and visit context. Register on fhir.eclinicalworks.com/ecwopendev.

THE 30-DAY NOTICE COMMITMENT IS WORTH SOMETHING. They have put in writing that any future fee comes with 30 days' warning. That means we can build against free today without a cliff risk we cannot see coming — unusual, and worth noting when we compare against vendors with unpublished pricing.

The gap, as everywhere: certified FHIR is read-only and excludes balances. Ask about write-back on the first call so we know the shape of the second track early.

## Action steps
1. [ ] Register on the provider developer portal at fhir.eclinicalworks.com/ecwopendev.  _(Claude)_
2. [ ] Call 508-836-2700 and ask for the Interoperability team; ask the write-back and balances questions.  _(Rick)_
3. [ ] Build the read-only integration on the free tier to prove the product.  _(Claude)_

## Open questions
- [ ] Does write-back of a note or communication log require a commercial agreement, and what does it cost?
- [ ] Is patient balance / accounts-receivable data available through any API, certified or proprietary?
- [ ] Are there plans to introduce fees, and would the 30-day notice apply to existing integrations?

## Log
- 2026-09-20 — seeded.

## Sources
- https://www.eclinicalworks.com/resources/certified-ehr-technology/
- https://fhir.eclinicalworks.com/ecwopendev/
- https://www.eclinicalworks.com/products-services/interoperability/
