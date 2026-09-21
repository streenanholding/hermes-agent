# Epic

- **Vendor:** Epic Systems Corporation
- **Deployment:** Cloud / health-system hosted.
- **Status:** LIVE PATH
- **Priority:** 3 — free to start, but the health system is the real gate
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Email vendorservices@epic.com asking for written confirmation that Vendor Services is not required for production client IDs.

## Why it matters
Largest health system footprint in the country. Relevant for hospital-affiliated and large medical groups rather than dental. Reputationally closed, but the documentation says otherwise.

## What they require
- CONFIRMED — Epic on FHIR (fhir.epic.com) describes itself as 'a free resource for developers.' FHIR R4, SMART on FHIR, CDS Hooks.
- CONFIRMED and widely misreported — Epic Vendor Services is OPTIONAL. Epic's own documentation: 'Vendor Services offers an optional suite of benefits including the ability to request individualized assistance with your app's data exchange.'
- CONFIRMED — the API Subscription Agreement is signed by the EPIC CUSTOMER (the health system), not by us. Fees under it are paid by the health system, quarterly, based on usage.
- CONFIRMED — process involves three parties: the developer, the Epic community member, and Epic. We register the app; the customer downloads our client record by client ID.
- NOT CONFIRMED — timeline. Not published. The health system's own integration governance queue is the real bottleneck, and it is slow and political.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| fhir.epic.com sandbox and client registration | Free | n/a | CONFIRMED |
| Epic Vendor Services (optional) | Not published by Epic | Us | NOT CONFIRMED — third-party claims of ~$1,900/yr contradict Epic's own docs |
| Showroom listing | Not published by Epic | Us | NOT CONFIRMED — ask |
| Health system API subscription | Not published | The health system | NOT CONFIRMED — ask |

## Contacts (published only — nothing invented)
- **Free developer programme:** https://fhir.epic.com/
- **Optional paid programme:** https://vendorservices.epic.com/
- **Customer-facing marketplace:** https://showroom.epic.com/
- **Email:** vendorservices@epic.com
- **Address:** 1979 Milky Way, Verona, WI 53593

## The play
The single most useful thing we can do with Epic costs nothing and takes one email: get Epic to confirm IN WRITING that Vendor Services is not required to register production client IDs. Epic's own documentation says it is optional; multiple consultancies say it is mandatory. That one answer resolves the biggest cost uncertainty on this list and, if it comes back as we expect, we get Epic for free.

Understand where the real friction is. It is not Epic's paperwork — it is the health system's integration governance committee, which meets on its own schedule and prioritises its own projects. That means the winning move is to let a motivated customer pull us through rather than pushing from outside. Do not treat Epic as a 90-day target unless a specific health system is actively asking for us.

Epic is not a dental play. Park it behind the dental systems and the easier medical ones unless a large medical group or hospital-affiliated DSO brings it to us.

## Action steps
1. [ ] Email vendorservices@epic.com asking for written confirmation that Vendor Services is not required for production client IDs.  _(Rick)_
2. [ ] Register a free developer account at fhir.epic.com and work the sandbox — costs nothing, proves the integration.  _(Claude)_
3. [ ] Do not pursue further without a specific health system asking for us.  _(Rick)_

## Open questions
- [ ] Is Vendor Services required to register production client IDs, or is it genuinely optional as your documentation states?
- [ ] What does Vendor Services cost, and what does a Showroom listing cost?
- [ ] What is a realistic timeline from registration to a first live customer connection?

## Log
- 2026-09-20 — seeded.

## Sources
- https://fhir.epic.com/
- https://fhir.epic.com/Documentation?docId=managingclients
- https://fhir.epic.com/Download/ApiLicenseAgreement
- https://vendorservices.epic.com/
