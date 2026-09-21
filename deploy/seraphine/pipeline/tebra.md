# Tebra (formerly Kareo + PatientPop)

- **Vendor:** Tebra
- **Deployment:** Cloud.
- **Status:** GATED
- **Priority:** 2 — cheapest confirmed full commercial path on the entire list
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Model the call volume against the 10,000/month free tier before committing to the $3,000.

## Why it matters
The only vendor that publishes a complete, precise fee schedule. At $3,000/yr plus free calls under 10,000 a month, this is the one place we can buy full commercial capability on a seed-stage budget.

## What they require
- CONFIRMED — two APIs. A SOAP API (proprietary, PM/billing — this is where PATIENT BALANCES live) and a FHIR API (R4, US Core 3.1.1, USCDI v1) via the appSphere developer portal.
- CONFIRMED — patient FHIR read needs no contract: 'There is no requirement for contracting with Tebra, Inc for the API read (GET) for USCDIv1 data for Patient APIs.'
- CONFIRMED — clinician-focused and bulk-export apps 'require business engagement documents and additional fees.'
- CONFIRMED — process: register on appSphere, complete developer profile, register the app with SMART scopes, Tebra reviews and approves.
- CONFIRMED — 10 GB data usage limit on API accounts.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Developer platform fee | $3,000 per year | Us | CONFIRMED |
| API calls — under 10,000/month | $0.000 per call | Us | CONFIRMED |
| API calls — 10,000 to 100,000/month | $0.005 per call | Us | CONFIRMED |
| API calls — 100,000 to 1,000,000/month | $0.008 per call | Us | CONFIRMED |
| API calls — over 1,000,000/month | $0.010 per call | Us | CONFIRMED |
| Patient USCDI v1 GET | Free, no contract required | n/a | CONFIRMED |

## Contacts (published only — nothing invented)
- **Partner portal:** https://partnerportal.tebra.com/English/
- **Partners page:** https://www.tebra.com/partners
- **API and integration documentation:** https://helpme.tebra.com/Tebra_PM/12_API_and_Integration
- **appSphere FHIR developer portal:** https://fhir.prd.cloud.tebra.com/appsphere/portal/#/login
- **Phone:** (866) 938-3272 — ask for the Integrators & EHR Platforms partner team
- **Address:** 1111 Bayside Drive, Suite 270, Corona Del Mar, CA 92625
- **Partner / BD email:** NOT PUBLISHED — use the partner portal or the 866 number.

## The play
This is the budget decision that unlocks the most capability for the least money, and it is the one place on this list where we can model the cost precisely before committing.

RUN THE NUMBERS BEFORE SIGNING. At under 10,000 calls a month the calls are free, so the real cost is the flat $3,000/yr. Work out how many practices and how many treatment plans per practice keep us under 10,000 — that number tells us exactly when the variable cost starts, and it is likely much later than instinct suggests. If we stay in tier 1, Tebra is $250 a month for a complete, contracted, write-capable integration.

THE SOAP API IS WHERE BALANCES LIVE. Certified FHIR does not expose patient accounts-receivable anywhere in the industry. Tebra's SOAP API does. That makes Tebra one of the few places we can get the complete picture — treatment, contact, balance and write-back — through one documented, priced relationship.

START FREE WHILE THE CONTRACT IS IN FLIGHT. Patient USCDI GET needs no contract at all. Build against it immediately and have something working before the commercial paperwork completes.

## Action steps
1. [ ] Model the call volume against the 10,000/month free tier before committing to the $3,000.  _(Claude)_
2. [ ] Register on appSphere and build against the free patient USCDI GET while the contract is negotiated.  _(Claude)_
3. [ ] Call (866) 938-3272, ask for Integrators & EHR Platforms, and start the commercial agreement.  _(Rick)_

## Open questions
- [ ] Does the $3,000 annual platform fee cover both the FHIR and SOAP APIs, or are they contracted separately?
- [ ] Is the 10 GB data limit annual or monthly, and what happens on exceeding it?
- [ ] What specifically are the 'business engagement documents' for clinician-focused apps?
- [ ] Does the SOAP API expose patient balance and payment plan data?

## Log
- 2026-09-20 — seeded.

## Sources
- https://www.tebra.com/tebra-partner-terms-and-conditions
- https://helpme.tebra.com/Tebra_PM/12_API_and_Integration
- https://www.tebra.com/wp-content/uploads/2023/08/FHIR_API_Documentation_01.pdf
