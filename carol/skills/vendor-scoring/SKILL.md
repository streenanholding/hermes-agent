---
name: vendor-scoring
description: Carol's scoring method for clearinghouse and gateway partners in FV-RFP-2026-01 and later re-bids. Use when ranking vendors, scoring proposals, or recommending how many partners to award.
version: 1.0.0
---

# Scoring connectivity partners

Pass/fail first (any fail = not eligible): BAA; SOC 2 Type II; CAQH CORE certification;
CMS HETS access; US-only PHI (offshore access disclosed and scored down); accepts that it
does all X12 processing; allows re-billing fallback costs to clinics.

Then 100 points, same weights as the RFP:
| Criterion | Points |
|---|---|
| Price and total cost (reference mix at Bands C and D, step-down, savings share) | 30 |
| Payer coverage (HETS, all 51 Medicaid programs, MA, commercial, dental) | 20 |
| Real-time performance and reliability (90-day p95, availability) | 15 |
| Automation and API quality (zero-touch practice and enrollment, sub-accounts, webhooks) | 15 |
| Security and compliance | 10 |
| Implementation, support, stability | 10 |
Sandbox validation on the fixed synthetic test set moves a finalist up to ±10.

FinVerified tie-breakers: dental benefit depth; reading ERAs without moving the clinic's
enrollment; Florida government coverage first; responsiveness during the RFP.

## How many to award
Default: **two or three partners**, each with a clear job —
1. **Primary real-time rail** (eligibility, claim status, ERA, enrollment by API).
2. **Secondary rail** for failover and payers the primary cannot reach.
3. **Dental-depth partner** if neither rail returns full dental benefit detail.
Recommend one partner only if it wins every role and offers strong failover. Show the cost
of each extra partner against the risk it removes.

## Output to Rick
A table: rank, vendor, score, proposed role, price at Bands B and C, coverage gaps, red
flags, NOT CONFIRMED items. Then a three-line recommendation and the decision Rick needs.
