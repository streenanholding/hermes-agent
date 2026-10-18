---
name: payverified-costs
description: How Carol measures and cuts PayVerified's running cost while raising quality. Use for the monthly cost report, any savings idea, routing decisions between connection sources, and vendor price reviews.
version: 1.0.0
---

# PayVerified cost engine

## The two numbers that matter
1. **Cost per reconciled claim** = all connectivity + data + AI cost for the month ÷ claims
   reconciled end to end (benefits → estimate → remittance matched).
2. **Cost per correct eligibility answer** = eligibility spend ÷ answers that were complete
   and matched what the payer actually paid.
Report both monthly, overall, per clinic, per payer and per source. A cheap answer that is
wrong costs more later.

## Source waterfall — always the cheapest source that gives a correct answer
1. **Free data first:** what the clinic's PMS already holds (plans, benefits, history,
   prior ERAs), public fee schedules and price-transparency files, CMS and payer FHIR APIs
   as they come online.
2. **The clinic's own clearinghouse** (already paid by the clinic).
3. **Our primary partner,** then the **secondary** for failover or coverage gaps, routed
   per payer by a live score of price × quality × speed.
4. **Human or portal work last,** and only through the clinic staff's own session.

## Standing savings levers (check monthly)
- **Reuse, don't re-ask:** reuse a fresh, complete eligibility answer for the same patient,
  payer and visit window; re-check only on a trigger (new plan, new month, procedure change,
  long gap, payment about to be taken).
- **Batch what can wait:** run next-day schedules in batch where batch is cheaper.
- **Never pay for failures:** partners bill only successful transactions; audit invoices
  against our own ledger monthly and claim credits.
- **Kill duplicates:** count duplicate requests within 24 hours by clinic; fix the cause.
- **Route by payer:** if one partner is cheaper or better for a payer, route it there.
- **Push volume tiers:** know where we sit in each band and when the next tier starts.
- **Direct and free connections:** for top payers by volume, check free provider APIs or
  direct connections worth using.
- **Step-downs and savings share:** enforce the yearly step-down and 50/50 savings share
  from the RFP; propose savings ideas to partners and log the split.
- **Quarterly market check:** if a partner falls behind the market, give 30 days to match
  before shifting share.
- **AI cost:** cheapest accurate model per job; cache stable context; no polling loops.

## Monthly report (one screen, details in a file)
1. Spend vs last month, and cost per reconciled claim vs last month.
2. Quality: first-pass eligibility success, benefit completeness, estimate accuracy, ERA
   delay.
3. Where we overpaid (by source, payer, clinic), with dollars.
4. Top three changes: what, dollars saved per month, risk, who does it.
5. Pass-through: what each fallback clinic was billed, and which clinics could save by
   connecting their own clearinghouse.
