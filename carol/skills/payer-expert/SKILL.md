---
name: payer-expert
description: Carol's expert reference on U.S. payers, government health programs, clearinghouses, X12/FHIR standards, enrollment, remittance, reconciliation and payment integrity. Use for any question about how a payer, program, rule or transaction works, and before advising Rick or drafting anything a payer or vendor will read.
version: 1.0.0
---

# Payer and payment-systems expert reference

Facts here are a starting map. Payer rules, plan line-ups, fees and deadlines change.
Before relying on any specific rule, date, payer ID or price, check the current official
source (CMS, the state Medicaid agency, the payer's provider manual, the vendor's docs) and
cite it. Mark anything you could not confirm as NOT CONFIRMED.

## 1. Who pays

**Commercial (employer and individual).** National carriers (UnitedHealthcare, Elevance /
Anthem, Aetna, Cigna, Humana for Medicare Advantage), the independent Blue Cross Blue
Shield companies (each its own payer with its own rules and portal), regional and provider-
owned plans, and integrated systems such as Kaiser. Self-funded employer plans (ERISA) are
administered by a carrier or TPA but follow federal, not state, insurance rules — this
matters for prompt-pay and surprise-billing questions.

**Medicare (federal, CMS).**
- Part A (facility) and Part B (professional) are processed by Medicare Administrative
  Contractors (MACs) by jurisdiction. Know which MAC covers each clinic's state (Florida:
  First Coast Service Options, jurisdiction N — verify on the cms.gov MAC map).
- Eligibility: the CMS HIPAA Eligibility Transaction System (HETS), real-time 270/271,
  reached through an approved submitter or clearinghouse.
- Provider enrollment: PECOS (CMS-855 forms), reassignment (855R), EFT (CMS-588), ERA
  enrollment with the MAC.
- Medicare Advantage (Part C): run by private plans; eligibility and claims go to the plan,
  not the MAC. HETS shows MA enrollment but not the plan's benefits.
- Traditional Medicare covers very little routine dental; MA plans often add dental
  through a dental carrier — a common reconciliation trap.

**Medicaid and CHIP (state-run, federally matched).** Each state runs its own program
through a fiscal agent / MMIS for fee-for-service and contracts managed-care plans (MCOs)
for most enrollees. Dental is often carved out to separate dental plans or an
administrative services organization. Eligibility can change month to month — check on
the date of service, not the date of booking.
- **Florida:** AHCA runs Medicaid through Statewide Medicaid Managed Care, with dental
  through contracted prepaid dental plans. Confirm current plans and payer IDs on the AHCA
  site before mapping.
- **California (Medi-Cal):** DHCS; Medi-Cal Dental runs largely fee-for-service through an
  administrator, with dental managed care in some counties. Confirm current structure.
- Medicaid is the payer of last resort — coordinate benefits with any other coverage first.

**Other government payers.** TRICARE (military; regional contractors), VA Community Care
(regional networks), Indian Health Service and tribal programs, FEHB plans, state employee
plans. Workers' compensation and auto insurance follow state rules and are not group health.

**Dental carriers.** Delta Dental member companies (each separate), MetLife, Cigna Dental,
Aetna Dental, Guardian, United Concordia, Humana Dental, Ameritas, Principal, the BCBS
dental plans, and Medicaid/MA dental plans such as DentaQuest, MCNA and LIBERTY. Dental
271s often omit frequency limits, history, waiting periods, age limits and downgrades —
the details that decide what the patient really owes.

## 2. The transactions (HIPAA X12 5010) — partners process these, we never build them

| Need | Transaction | Notes |
|---|---|---|
| Is the patient covered, what are the benefits | 270 / 271 | Real-time; quality varies hugely by payer |
| Where is the claim | 276 / 277 | Real-time or batch |
| Claim acknowledgment | 999, 277CA | Front-end acceptance and rejection |
| Submit a claim | 837P (professional), 837I (institutional), 837D (dental) | |
| Payment explanation | 835 (ERA) | One ERA destination per payer per provider |
| Prior authorization | 278; FHIR Da Vinci PAS | |
| Attachments | 275 or vendor channels | Dental x-rays and narratives often via vendor |
| Payment | EFT via ACH CCD+; reassociate to 835 with the TRN segment | |

**CAQH CORE operating rules** set the bar for eligibility, claim status and ERA/EFT,
including response-time and content rules and EFT/ERA enrollment data sets. Use them as
the minimum standard when grading partners and payers.

**FHIR and CMS-0057-F (Interoperability and Prior Authorization final rule).** Impacted
payers (Medicare Advantage, Medicaid and CHIP programs and plans, ACA exchange plans)
must stand up Provider Access, Payer-to-Payer and Prior Authorization APIs, with most API
requirements due January 2027 and faster prior-auth decision timeframes earlier. These are
free, standards-based data sources to plan around. Verify current dates on cms.gov.

**Price transparency.** Transparency in Coverage machine-readable files publish
in-network negotiated rates; hospital price files publish standard charges. Useful for
expected-payment checks. No Surprises Act Good Faith Estimates apply to uninsured and
self-pay patients.

## 3. Enrollment — the slow part that decides go-live

For each clinic and payer there can be four separate enrollments: claims (837), ERA (835),
EFT (payment), and sometimes eligibility. Some payers need none for claims through a
clearinghouse; most need ERA and EFT enrollment. Tools: CAQH ProView (credentialing data),
CAQH EnrollHub (EFT/ERA for many payers), payer portals, clearinghouse enrollment APIs.
Durations run from same day (API-enrolled payers) to 30–60+ days (some Medicaid, some
Blues, paper forms). Track every one; never let one sit.

**Observe-first rule:** a payer sends the ERA to one place. Enrolling ERA with a new
clearinghouse can move it away from the clinic's current system. Never do that unless the
clinic opts in knowing the effect.

## 4. Reconciliation — what PayVerified certifies

The chain: benefits (271) → estimate (allowed amount, deductible, coinsurance, frequency
rules) → patient responsibility certified before payment → claim (837) → acknowledgment →
status → remittance (835) and EFT → match → post → flag differences → work item.
Common causes of mismatch: coordination of benefits, frequency/history limits, downgrades
(dental), out-of-network allowed amounts, missing pre-auth, bundling and NCCI edits,
timely-filing denials, eligibility changed after booking, MA vs traditional Medicare
confusion, Medicaid retro-eligibility. Know CARC/RARC codes on the 835 and translate them
into plain English for clinics and patients.

## 5. Payment integrity and government buyers
- Medicare: NCCI edits and MUEs, LCDs/NCDs, Recovery Audit Contractors, UPICs, CERT.
- Medicaid: state program-integrity units, Medicaid Fraud Control Units, state OIGs.
- What payers value from PayVerified: proof the service happened (Care Confirmations),
  fewer improper payments, fewer appeals, clean data. Speak their language: improper
  payment rate, recoveries avoided, administrative cost per claim.

## 6. Timely filing and appeals (verify per payer)
Medicare: generally 12 months from date of service for claims. Medicaid and commercial
vary widely (often 90–365 days). Appeal windows are separate and often short. Always check
the payer's current provider manual and record the rule with its source in the payer file.

## 7. The connectivity market (how to judge a partner)
API-first clearinghouses (modern JSON APIs, fast onboarding), large legacy networks (huge
coverage, enterprise pricing, slower), dental specialists (deep dental benefit detail,
attachments), eligibility specialists (benefit parsing, coverage discovery), and low-cost
networks (cheap, often SFTP/batch). Judge on: real coverage by payer and transaction,
real-time share, benefit completeness, latency, zero-touch enrollment by API, per-practice
sub-accounts and usage data, ability to read ERAs without changing the clinic's
enrollment, security (SOC 2 Type II, HITRUST, breach history), and price at our volume.
