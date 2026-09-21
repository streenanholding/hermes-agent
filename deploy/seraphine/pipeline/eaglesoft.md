# Eaglesoft — Patterson Dental   ★ PRIORITY 1

- **Vendor:** Patterson Dental (Patterson Companies)
- **Deployment:** On-premise. Runs Sybase SQL Anywhere on a server in the practice.
- **Status:** GATED
- **Priority:** 1 — clinics are launching on this first
- **Owner:** Rick
- **Last action:** 2026-09-20 — tracker seeded from Partnership Plan workbook
- **Next action:** Open the PIC software providers page and complete the Authorized Vendor Request Form. Follow the submission instructions printed on the form.

## Why it matters
Our first launching clinics run Eaglesoft. Nothing else on this list is time-critical the way this is. Patterson is one of the two dominant dental PMS vendors alongside Henry Schein One.

## What they require
- CONFIRMED — Patterson Innovation Connection (PIC) is restricted to authorized technology partners. The API specification itself sits behind the partnership; you do not get it by asking a clinic.
- CONFIRMED — Patterson publishes a list of authorized vendors and warns practices in writing: 'some providers and vendors have built integrations and interfaces to Eaglesoft without authorization or communication with Patterson. We strongly encourage you to only use services from the below authorized vendors.' Being outside that list is a sales problem, not just a technical one.
- CONFIRMED — the front door is the Authorized Vendor Request Form (Patterson support answer 6595), submitted from the Patterson Innovation Connection software providers page.
- CONFIRMED — there are four commercial tiers. The one that fits us is VENDOR DIRECT: purchased, supported and billed directly through the vendor. Patterson authorizes; they do not bill or support. Lowest friction.
- CONFIRMED — the API runs as a component installed on the practice's own Eaglesoft server. It auto-installs from Eaglesoft 19.1; versions 18.0–18.1 need a manual install. The integrating application authenticates with an Eaglesoft server URL, username and password that the practice controls.
- NOT CONFIRMED — whether PIC carries an application fee, membership fee or per-connection royalty. Nothing on fees appears on any page we could read. Must ask.
- NOT CONFIRMED — Patterson's written position on reading the Sybase database directly. Must ask.

## Costs
| Item | Amount | Who pays | Confirmed? |
|---|---|---|---|
| PIC application / membership fee | Not published | Us (presumed) | NOT CONFIRMED — ask |
| Per-connection or per-practice royalty | Not published | Unknown | NOT CONFIRMED — ask |
| Eaglesoft API component | Installed on practice server; auto-installs 19.1+ | Practice | CONFIRMED |

## Contacts (published only — nothing invented)
- **Patterson sales team (the number published for authorized-vendor questions):** 800.294.8504
- **Authorized Vendor Request Form:** pattersonsupport.custhelp.com/app/answers/detail/a_id/6595
- **Form lives on:** pattersondental.com/cp/software/dental-practice-management-software/patterson-innovation-connection-software-providers
- **Third-party integrations list (read this before any call):** pattersonsupport.custhelp.com/app/answers/detail/a_id/18100
- **PIC vendor API information:** pattersonsupport.custhelp.com/app/answers/detail/a_id/29059
- **Download and install Eaglesoft API:** pattersonsupport.custhelp.com/app/answers/detail/a_id/23926

## The play
Three levers, in order of power.

1. USE THE CLINIC. A cold vendor application from an unknown startup sits in a queue. An existing Eaglesoft practice calling Patterson to say 'we have bought FinVerified and we need them authorized' is a customer request, and customer requests move. Ask our launching clinic to make that call to 800.294.8504 in the same week we submit the form. This is the single highest-leverage thing we can do and it costs nothing.

2. ASK FOR VENDOR DIRECT, BY NAME. Patterson's own page defines four tiers. Vendor Direct means we bill and support our own customers and Patterson simply authorizes the integration — no Patterson billing relationship, no Patterson support burden, no revenue share to negotiate. Naming that tier in the application signals we have done our homework and removes their biggest objection, which is support load.

3. LEAD WITH SECURITY, BECAUSE THEY DO. Patterson's integrations page is written almost entirely about privacy and cybersecurity risk — it is what they care about. Our application should open on read-oriented scope, hashed patient identifiers, no clinical writes, and BAAs with every practice. We are asking for less access than most vendors on their list, and we should say so plainly.

⚠ CONFLICT TO HANDLE HONESTLY: Patterson CarePay+ is Patterson's own patient financing product, sold through Patterson. If we walk in looking like a financing competitor we will not get authorized. Position FinVerified as the compliance and disclosure layer that sits over ANY financing pathway — including CarePay+ — and makes the practice defensible. That framing makes us complementary to their product rather than a threat to it. Do not improvise this on the call; agree the wording with Nancy first.

## Action steps
1. [ ] Open the PIC software providers page and complete the Authorized Vendor Request Form. Follow the submission instructions printed on the form.  _(Rick)_
2. [ ] Same week: ask the launching clinic to call Patterson at 800.294.8504 and request FinVerified be authorized.  _(Rick)_
3. [ ] Agree the CarePay+ positioning wording with Nancy before any Patterson call.  _(Rick + Nancy)_
4. [ ] Open support answers 18100, 29059 and 23926 in a browser and read the expandable sections — they are blocked to automated tools but open fine for a person.  _(Rick)_
5. [ ] BLOCKER ON OUR SIDE, INDEPENDENT OF PATTERSON: build the tunnel server that answers the bridge agent. It does not exist. Until it does, Eaglesoft cannot connect even with authorization.  _(Claude)_
6. [ ] Stamp the clinic ID during installer setup and make the auto-updater actually install.  _(Claude)_

## Open questions
- [ ] Is there an application fee, annual membership fee, or per-connection royalty for PIC?
- [ ] What are the specific criteria to become an authorized technology partner?
- [ ] How long does authorization typically take from form submission?
- [ ] Can we be listed under Vendor Direct Solutions — vendor billed, vendor supported?
- [ ] What is Patterson's written position on reading the Eaglesoft database directly versus using the PIC API?
- [ ] Does authorization cover all Eaglesoft versions from 18 up, or only current releases?
- [ ] Is there any conflict from Patterson's side given CarePay+ is a financing product?

## Log
- 2026-09-20 — seeded.

## Sources
- https://pattersonsupport.custhelp.com/app/answers/detail/a_id/18100  (updated 3 Sep 2026)
- https://pattersonsupport.custhelp.com/app/answers/detail/a_id/6595  (updated 13 Apr 2026)
- https://pattersonsupport.custhelp.com/app/answers/detail/a_id/29059
- https://www.dentalcompare.com/News/334094-New-Dental-Product-Patterson-Innovation-Connection-PIC-from-Patterson-Dental/
- https://support.easyrxortho.com/portal/en/kb/articles/enabling-and-using-the-patterson-eaglesoft-integration
