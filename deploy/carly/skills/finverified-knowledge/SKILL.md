---
name: finverified-knowledge
description: Carly's reference on what FinVerified is, how it works, who it serves, how partners (lenders, processors, marketplaces, HSA/FSA benefits providers like Opus Health) connect, pricing, team and standing rules. Use before answering any question about FinVerified, preparing Rick for a call, or drafting anything a customer or partner will read.
version: 1.0.0
---

# FinVerified knowledge base (as of Oct 19, 2026)

Facts here are Rick's decisions as of the date above. Things change fast: if a fact matters
(a price, a date, whether a feature is live), say "as of Oct 19" or ask Rick to confirm.
Never promise a partner that something is live unless Rick has said it is live.

## What FinVerified is
- FinVerified, Inc. is a Payment Pathway Compliance(TM) SaaS platform. It governs the patient
  payment conversation (financing, in-house plans, card and benefits payments) at dental,
  medical, hospital and veterinary practices in all 50 states plus DC.
- It documents every disclosure shown to a patient with sealed, time-stamped proof, and keeps
  the clinic compliant with consumer-credit and provider-conduct rules (MCF(R) standard,
  from Finance Rx, acquired in 2026).
- FinVerified never provides, arranges or services financing, never processes payments, and
  never holds or moves money. The clinic is always merchant of record. FinVerified takes no
  cut of patient payments (Oct 16, 2026 ruling).
- Delaware corporation. Office: 11718 SE Federal Hwy, Suite 202, Hobe Sound, FL 33455.

## How it works for a clinic
1. Clinic presents a treatment plan and sends the patient a Magic Link.
2. Patient verifies ID once (ID scan + face, or a one-time-code fallback; nobody is blocked).
3. Patient sees every way to pay, in order (the "waterfall"): benefits (HSA/FSA) first, then
   pay in full or an in-clinic plan (up to 4 payments, no interest), then licensed lender
   offers on the remaining balance.
4. Patient chooses and consents on their phone. Everything is sealed as evidence.
5. Payments are reconciled automatically. FinVerified complements the clinic's existing card
   processor; it never replaces it.
- PMS connections (Open Dental, Dentrix, Eaglesoft): instant updates and payment posting into
  the clinic ledger. Any vendor fee is passed through at cost as "<PMS> Connect Fee".

## Pricing (clinics)
- $468/location/month month-to-month; $398/location/month with a 12-month agreement;
  $4,298.40/location/year prepaid. Plus $6.99/month per active team member (every person has
  their own login; never say "per login"). Clinics pay by ACH. 30-day free trial.
- Partners (lenders, processors, marketplaces, benefits providers) join free.

## Partners and how they connect
- Partner types: Lenders, Marketplaces, Processors, Benefits & Allowances providers. One
  account can hold several roles, set per clinic.
- Onboarding is self-serve, Stripe-Connect style: no FinVerified person is needed to join,
  connect or go live. Partner contact: partners@finverified.ai.
- Connection options: API; point existing webhooks at FinVerified; read-only, revocable
  "Connect" buttons; forward existing reports. No CSV uploads. FinVerified never collects SSNs
  or loan repayment data.

## Benefits & Allowances (HSA/FSA) and Opus Health
- Open category (HSA, FSA, LPFSA, HRA, LSA, Medicare Advantage allowances, flex cards). Opus
  Health is the first provider; nothing is Opus-specific. Free to join; no revenue share.
- Capabilities a provider turns on: Find (benefits lookup), Pay (HSA/FSA at checkout),
  Pay-me-back (reimburse after checkout from FinVerified's itemized receipt).
- Patient rule: at most one tap, no typing. All providers asked at once; 3-second cutoff
  (target under 2s); on timeout the line just doesn't show.
- Standard contract (same for every provider): calls POST /eligibility, /apply, /cancel;
  signed webhooks payment.authorized, payment.settled, substantiation.completed,
  payment.refunded, payment.disputed. HMAC-signed, retried, duplicates ignored. Sandbox + mock
  provider; automated round trip (eligibility, apply, settle, refund) flips a provider live.
- Data: name, DOB, zip, procedure codes, amount, consent token only. SSN never enters
  FinVerified; if needed, the provider hosts a secure field inside the Magic Link. BAA before
  go-live. FinVerified sends all patient reminders in the clinic's name; providers trigger
  them by API.
- STATUS (as of Oct 19): the module is built behind a switch that is OFF in production, and the
  integration contract is designed but not yet built. Never tell a partner it is live.
- Opus contacts: Carolina Rojas, Samuel Kennedy; their CTO. Product walkthrough Wed Oct 21.
  Opus is an HSA/FSA processor; it earns on processing. Open questions for Opus: API docs and
  sandbox, match rate without SSN (is last-4 enough?), merchant setup by API, med spa
  declines (spa merchant codes), lookup fees (push for free lookups), reimbursement docs,
  administrators covered, Medicare Advantage/flex cards.

## Partnerships
Every entry below is status: ask Rick for the latest. Never tell anyone a deal stage or a date from this list without checking with Rick first.
- **Opus Health**: HSA/FSA Benefits & Allowances partner. Contact: Carolina. Being ramped onto self-serve partner onboarding. Status: ask Rick for the latest.
- **Dentirate**: second onboarding partner. Status: ask Rick for the latest.
- **Cordoba Legal**: Payment Pathway Legal Defense Plan. Counterpart: Dan. Pricing is under negotiation. Status: ask Rick for the latest.
- **Lender network / marketplace**: the lenders and marketplaces that connect through partner onboarding. Status: ask Rick for the latest.
- **Advisors**: Jeff (policy and government affairs) and Dr. Diana Fat. Status: ask Rick for the latest.

## PayVerified(TM)
- Second product: revenue-cycle and payment-integrity suite (real-time insurance
  reconciliation, denied-claim recovery). Gated and not publicly launched. Flat pricing, uses
  the clinic's own clearinghouse first. Carol (Director of PayVerified) runs it. HSA/FSA is
  left to partners like Opus, not PayVerified.

## People and agents
- Rick Hennessey: Executive Chairman and co-founder. Nancy Kay Coy: CEO and co-founder
  (ncoy@finverified.ai). Outside counsel: Chuck Washburn (Manatt). Engineering contractor:
  Ashish (Mango IT).
- Agents: Carly (Chief of Staff), Sol (CFO), Seraphine (Head of IT), Carol (Director of
  PayVerified).

## Words and style
- In anything people read, write the wordmark Fin✓erified (and Pay✓erified™). Plain
  "FinVerified" only in legal entity names, email subjects, URLs and code.
- Never use: "WellFit", "FV-Verified", "FV-Clear", "C.L.E.A.R.", "Solutions Architect", "per
  login". The certified status is simply "FinVerified" ("Are you FinVerified?").
- Ticket numbers: never write a bare FIN-xxx; always add what it is.
- Keep RevTurn and HouseAm separate from FinVerified.
