# Dentrix and Dentrix Ascend — Henry Schein One

- **Vendor:** Henry Schein One
- **Deployment:** Dentrix = on-premise, Microsoft SQL Server, reached by ODBC. Ascend = cloud, REST API.
- **Status:** GATED
- **Priority:** 2 — biggest dental market share, highest cost to enter
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Get SOC 2 Type II started — engage an auditor and begin the observation period. Everything else on this tab waits on it.

## Why it matters
Dentrix is the largest name in dental practice management. We cannot claim dental coverage without it. It is also the most expensive and slowest door on this entire list, so the clock needs to start early even though we will not connect soon.

## What they require
- CONFIRMED — 'The Dentrix API Agreement is sent to be signed before receiving the API key.' A clinic cannot approve us into existence. The agreement comes first, for sandbox as well as production.
- CONFIRMED — a security assessment: 'Vendor subject to security assessment to ensure integration meets minimum standards.' All integrated vendors must be SOC 2 Type II and OAuth 2.0 certified.
- CONFIRMED — on-premise Dentrix is NOT a REST API. It is a password-protected ODBC connection plus DLL functions and stored procedures. The connection string is only obtainable by a signed, registered application: 'Your signed application authenticates using the RegisterUser function, which allows GetConnectionString to return the credentials needed for ODBC access.'
- CONFIRMED — the API key may not be transferred, sold, distributed, disclosed, sublicensed or lent. Violations terminate the agreement. There is no reseller or partner-of-a-partner route.
- CONFIRMED — Henry Schein One publicly names vendors it believes are connecting without authorization, and tells practices to check the approved list first.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Dentrix Ascend — one-time registration and set-up | $5,000 | Us | CONFIRMED |
| Dentrix Ascend — monthly, per location | $47 (incl. 30K calls, 3GB per location per month) | Us | CONFIRMED |
| Dentrix Ascend — overage | $0.0018 per call; $1.00 per GB | Us | CONFIRMED |
| Dentrix on-prem — one-time registration, READ | $5,000 | Us | CONFIRMED |
| Dentrix on-prem — one-time registration, WRITE | $5,000 (additional) | Us | CONFIRMED |
| Dentrix on-prem — monthly royalty | Based on API categories selected; rate card not published | Us | NOT CONFIRMED — ask |
| SOC 2 Type II audit | Not a Henry Schein cost, but a prerequisite they impose | Us | CONFIRMED as required |

## Contacts (published only — nothing invented)
- **Developer portal and FAQ (where the fees are published):** https://ddp.dentrix.com/pages/faq
- **API Exchange overview:** https://www.henryscheinone.com/dental-solutions/api-exchange/
- **Vendor-facing page and process:** https://www.henryscheinone.com/dental-solutions/api-exchange/api-exchange-vendors/
- **Authorized vendor list (and the unauthorized-vendor warning):** https://www.henryscheinone.com/dental-solutions/api-exchange/vendors-list/
- **Email / phone for developer enquiries:** NOT PUBLISHED — the vendor page uses a contact form. Must ask.

## The play
Do not apply yet. Apply when the gates are cleared and the demand is proven — otherwise we pay five figures for a key we cannot use.

THE REAL GATE IS SOC 2 TYPE II, AND IT IS A CLOCK, NOT A CHEQUE. We have SOC 2 policies written. A Type II report is different: an outside auditor observes the controls actually operating over a period of months. That period cannot be compressed by spending more. Starting that clock this month is worth more than any code we could write for Dentrix, because everything else here waits on it.

MAKE THE $47 SOMEONE ELSE'S LINE ITEM. The Ascend fee is explicitly per location per month. Price it into the clinic subscription from day one rather than absorbing it — at scale it is the difference between a margin and a leak. Decide this before we sign, because changing it later means repricing customers.

SEQUENCE THE $10,000. On-prem is $5,000 READ and another $5,000 WRITE. Our write is a single payment-status note. Start READ-only, prove the integration and the demand, and buy WRITE when the write-back is genuinely required. That halves the entry cost and defers the rest.

STAY OFF THE UNAUTHORIZED LIST. Henry Schein One names vendors publicly. Whatever we build for Dentrix clinics before authorization must not touch the Dentrix database — not in a pilot, not in a demo, not 'just for testing'. Our Manual Mode path exists for exactly this.

## Action steps
1. [ ] Get SOC 2 Type II started — engage an auditor and begin the observation period. Everything else on this tab waits on it.  _(Rick)_
2. [ ] Decide now whether the $47 per location per month is absorbed or passed through to the clinic subscription.  _(Rick + Nancy)_
3. [ ] Hold the application until (a) SOC 2 Type II is in progress and (b) we have committed Dentrix clinics to justify the $5k–$10k.  _(Rick)_
4. [ ] When applying: request READ scope only on on-prem Dentrix to start. Defer the WRITE $5,000.  _(Rick)_
5. [ ] Ask for the on-prem monthly royalty rate card in writing before signing anything.  _(Rick)_

## Open questions
- [ ] What is the monthly royalty rate card for on-premise Dentrix, and is it per location?
- [ ] How long from application to production credentials?
- [ ] How does a practice grant a specific vendor access inside Ascend — a consent screen, or do you provision it?
- [ ] Does the security assessment require SOC 2 Type II already complete, or is Type I plus a Type II in progress acceptable?
- [ ] What is the current status of the Dentrix Connected certification, separate from API Exchange authorization?
- [ ] Is the $5,000 READ fee creditable against the WRITE fee if we add write scope later?

## Log
- 2026-09-20 — seeded.

## Sources
- https://ddp.dentrix.com/pages/faq
- https://www.henryscheinone.com/dental-solutions/api-exchange/api-exchange-vendors/
- https://www.henryscheinone.com/dental-solutions/api-exchange/vendors-list/
- https://investor.henryschein.com/news-releases/news-release-details/2023/Henry-Schein-One-Announces-Dentrix-Ascend-API-Exchange-07-13-2023/
