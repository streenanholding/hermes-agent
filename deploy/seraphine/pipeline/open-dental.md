# Open Dental   ✓ OUR REFERENCE IMPLEMENTATION

- **Vendor:** Open Dental Software
- **Deployment:** Both. Cloud-hosted, and on-premise with a local API service.
- **Status:** IN MOTION
- **Priority:** 1 — already moving, and the only true self-serve story in dental
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Email sent to vendor.relations@opendental.com requesting Developer Portal access. Awaiting reply (1–3 business days).

## Why it matters
The only dental PMS where a clinic clicking approve is genuinely enough. That makes it the honest version of the story we want to tell in sales, and the right system to build and prove the onboarding flow against.

## What they require
- CONFIRMED — one-time developer registration by email to vendor.relations@opendental.com. Requests take one to three business days to process. That is the only published turnaround time of any vendor on this list.
- CONFIRMED — two-key model. A Developer API Key unique to us from the Developer Portal, and a Customer API Key unique to each customer/developer pair which we generate. The office then pastes it in at Setup > Advanced Setup > API > Add Key. That is a real click-approve moment, per clinic, with no further Open Dental involvement.
- CONFIRMED — direct database access via ODBC is documented and supported by Open Dental. The only stated restriction is that ODBC cannot be the data source for Open Dental's own client software. This is the one system where our on-prem approach breaks no rules.
- CONFIRMED — three deployment modes: Local (single workstation), Service (continuous, needs inbound firewall rule on port 30223), Remote (Open Dental's hosted API). Remote API requires the office to run an eConnector.
- CONFIRMED — Open Dental expects developers to hold a BAA with their clients. The HIPAA relationship is developer-to-clinic, not developer-to-Open-Dental.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| Read All permission | Free (throttled to 1 request per 5 seconds) | Per location | CONFIRMED |
| Comm, Documents, InsuranceSimple, Setup, Queries | $15 per location per month (1 req/sec) | Per location | CONFIRMED |
| All except Payments, PayPlans, Special | $30 per location per month | Per location | CONFIRMED |
| All except Special | $35 per location per month | Per location | CONFIRMED |
| Who is invoiced — us or the practice | Not stated on their pricing page | Unknown | NOT CONFIRMED — ask |

## Contacts (published only — nothing invented)
- **Developer portal access request:** vendor.relations@opendental.com
- **API setup and the two-key model:** https://www.opendental.com/site/apisetup.html
- **API specification:** https://www.opendental.com/site/apispecification.html
- **Permissions and pricing:** https://www.opendental.com/site/apipermissions.html
- **API modes — Local, Service, Remote:** https://www.opendental.com/site/apilocal.html
- **ODBC / direct database access:** https://www.opendental.com/manual/odbc.html
- **Forum thread we already opened:** opendentalsoft.com:8085/forum — topic 8700

## The play
We are already in motion here — the developer portal request went to vendor.relations@opendental.com. Two things to get right while we wait.

MAKE THIS THE PROOF. Open Dental is the only dental system where 'the clinic clicks approve and it connects' is true today. Build the onboarding flow against Open Dental first, get it genuinely seamless, and every other integration becomes a matter of swapping the adapter underneath a proven experience. Do not build the flow generically against a system we cannot test on.

GET THE BILLING ANSWER BEFORE WE QUOTE ANYONE. Their pricing is per location and they do not publish who is invoiced. At $15–$35 per office per month, across a few hundred offices, that is the difference between a line item and a business model problem. Ask it in the first email, not the fifth.

FIX THE WRITE-BACK. Our connector currently posts to /treatmentplans/{id}/paymentnote, which is not an Open Dental resource. Their real write target is Commlogs. This would have failed on the first live office. The developer-portal request already asks for Commlogs CREATE so the permission is right from the start.

## Action steps
1. [ ] Email sent to vendor.relations@opendental.com requesting Developer Portal access. Awaiting reply (1–3 business days).  _(Rick — DONE)_
2. [ ] Rewrite the adapter write-back from the non-existent paymentnote endpoint to a Commlogs entry, with tests.  _(Claude)_
3. [ ] When portal access arrives, forward the credentials and we generate the first Customer API Key.  _(Rick)_
4. [ ] Build the clinic-facing onboarding flow against Open Dental as the reference implementation.  _(Claude)_
5. [ ] Confirm whether the per-location fee is invoiced to us or the practice, and reflect it in pricing.  _(Rick)_

## Open questions
- [ ] Is the per-location API fee invoiced to us as the developer, or to the dental office?
- [ ] Is a signed developer agreement required beyond the portal request?
- [ ] For on-premise offices, do you recommend Service mode or the eConnector plus Remote API for a vendor in our position?
- [ ] Does the Commlogs create permission sit in the $15 tier (Comm) as we read it?

## Log
- 2026-09-20 — seeded.

## Sources
- https://www.opendental.com/site/apisetup.html
- https://www.opendental.com/site/apipermissions.html
- https://www.opendental.com/site/apispecification.html
- https://www.opendental.com/manual/odbc.html
