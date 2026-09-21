# athenahealth

- **Vendor:** athenahealth
- **Deployment:** Cloud.
- **Status:** GATED
- **Priority:** 3 — strong medical entry once the Marketplace gate is cleared
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Ask athenahealth in writing whether the certified FHIR API can be used against a consenting practice without Marketplace membership.

## Why it matters
Large ambulatory medical footprint and a well-run partner programme. Per-practice onboarding is genuinely fast once we are in; the gate is getting in.

## What they require
- CONFIRMED — Marketplace partner programme (successor to More Disruption Please). 800+ API endpoints with public documentation; ~240 partner organizations.
- CONFIRMED — vetting: 'we conduct some initial diligence on MDP Partners before allowing them to join the marketplace.'
- CONFIRMED — HITRUST self-assessment required within 90 days of being Generally Available.
- CONFIRMED — the clinic-side step is a signed authorization: 'Once you contract with the partner and sign the athenahealth authorization and consent form, the partner notifies the MDP Operations team.'
- NOTE — the FAQ carrying the fee and diligence statements is footered © 2016. Ten years old. Do not rely on the fee position without re-confirming.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| athenahealth interface / setup fee to connect a partner | None stated — 'athenahealth does not charge interface or setup fees' | n/a | CONFIRMED but from a 2016 document — re-confirm |
| Marketplace listing fee or revenue share | Not published currently | Unknown | NOT CONFIRMED — ask |
| athenaOne proprietary APIs | Reported pay-per-call | Us | NOT CONFIRMED — secondary source only |
| Data View (Snowflake replica, 24h latency) | Subscription | Unknown | NOT CONFIRMED — ask |

## Contacts (published only — nothing invented)
- **Marketplace programme:** https://www.athenahealth.com/solutions/marketplace-program
- **Partners page:** https://www.athenahealth.com/solutions/marketplace-partners
- **Developer portal:** https://www.athenahealth.com/developer-portal
- **Marketplace FAQ (© 2016 — dated):** https://www.athenahealth.com/~/media/athenaweb/files/marketplace/pdfs/faq.pdf
- **Direct email or phone for partner enquiries:** NOT PUBLISHED — apply through the Marketplace programme page.

## The play
The highest-value unknown on this tab is whether the Cures Act certified FHIR API lets us read clinical data from a consenting practice WITHOUT Marketplace membership. Federal information-blocking rules make that plausible, and athenahealth's own documentation is JavaScript-rendered so we could not read it. Find out before committing to the Marketplace timeline — if the answer is yes, we get a free read-only beachhead now and pursue Marketplace on our own schedule for the write-back.

The HITRUST self-assessment is a 90-days-after-GA obligation, not a precondition. That is a meaningful difference: we can be listed and live before it is done. Read the requirement carefully rather than treating it as another SOC 2 style clock.

Per-practice onboarding is 'a few days' once we are a partner. That makes athenahealth a good second medical integration after the free-tier systems — the marginal cost per new practice is low.

## Action steps
1. [ ] Ask athenahealth in writing whether the certified FHIR API can be used against a consenting practice without Marketplace membership.  _(Rick)_
2. [ ] Request current Marketplace terms — fees, revenue share, timeline — since the published FAQ is from 2016.  _(Rick)_
3. [ ] If the free FHIR path exists, build read-only against it first and defer Marketplace.  _(Claude)_

## Open questions
- [ ] Can the certified FHIR API be used against a consenting practice without Marketplace membership?
- [ ] Is the 'no interface or setup fee' position from the 2016 FAQ still current?
- [ ] What are current athenaOne per-call rates?
- [ ] What is the current Marketplace application timeline, and are there listing fees or revenue share?

## Log
- 2026-09-20 — seeded.

## Sources
- https://www.athenahealth.com/solutions/marketplace-program
- https://www.athenahealth.com/~/media/athenaweb/files/marketplace/pdfs/faq.pdf
- https://www.athenahealth.com/developer-portal
