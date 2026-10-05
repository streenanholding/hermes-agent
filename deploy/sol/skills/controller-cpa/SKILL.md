---
name: sol-controller-cpa
description: Controller and CPA-grade accounting: chart of accounts, founder funding buckets, backfill procedure, close package. Use for Xero drafts, month-end close, founder-paid expense schedule.
---

# Skill: Controller & CPA-grade bookkeeping

## Chart of accounts additions (propose to Rick before creating in Xero)
- 2300 Note Payable — Rick Hennessey (related party, current)
- 3100 Additional Paid-in Capital — Rick Hennessey contributions
- 6100 Contract Development — Mango IT Solutions (foreign contractor)
- 6200 Cloud Hosting & Infrastructure (AWS, Railway)
- 6210 AI Services (Anthropic/Claude, Bedrock, OpenRouter, LiteLLM)
- 6220 Monitoring & Security (Better Stack, Sentry until cancelled)
- 6230 SaaS & Productivity (Google Workspace, Linear, GitHub, Slack, Xero, etc.)
- 6400 Legal & Professional (Manatt, CPA)
- 1500 Capitalized Software (only if the CPA approves a capitalization policy — see below)

## Founder funding — the core 2026 backfill
Rick funded FinVerified personally in 2026. Two different buckets. Never mix them.

**Bucket A — $75,000 loan from Rick Hennessey (to be repaid).**
- Book: Dr expense or cash / Cr 2300 Note Payable — Rick Hennessey, dated when the money was spent or deposited.
- Required before any repayment (put each on the open-items list until done):
  1. A signed promissory note (amount, date, interest rate, repayment terms). If none exists, flag it; counsel drafts.
  2. Board consent approving the loan and repayment. Rick is an interested party, so the approval should come from a disinterested director (Nancy) and be documented (DGCL §144 safe harbor).
  3. Interest: a loan over $10,000 at 0% or below the IRS Applicable Federal Rate can trigger imputed interest (IRC §7872). Flag for the CPA; don't decide it yourself.
  4. Disclose the loan and any planned repayment from SAFE proceeds in the SAFE materials (use of proceeds). Flag for counsel.
- Repayment: draft a Mercury payment + a draft journal (Dr 2300 / Cr Cash). Rick releases. Never repay from investor funds without counsel's sign-off on disclosure.

**Bucket B — anything Rick paid beyond the $75,000 that he won't be repaid for.**
- Book: Dr expense / Cr 3100 Additional Paid-in Capital — Rick Hennessey. No shares, no repayment.
- Only after Rick confirms in Slack which payments are Bucket A and which are Bucket B.

**Pre-incorporation costs:** anything paid before FinVerified, Inc. existed is flagged separately (start-up and organizational cost rules, IRC §195/§248). The CPA decides treatment.

## Backfill procedure (Jan 1, 2026 → today)
1. Read every statement in **Payments Jan-Sept 2026**. Pick out FinVerified charges only.
2. Match each charge to an invoice/receipt (sol@ inbox, vendor portals, Drive). No receipt → open item.
3. Build the Sheet **Founder-Paid Expense Schedule 2026**: date | vendor | description | amount | account | bucket (A/B/?) | receipt link | paid-by (card last 4) | R&D flag | confidence | Rick to confirm.
4. Reconcile Mango: 38 weekly invoices MIT-FV-2026-W01…W38 total **$373,100.00** (all match the contract rate of $1,800/developer/week + $250/week PM). Confirm each was actually paid and from which account.
5. Show Rick the schedule. After he confirms, create Xero DRAFT manual journals, one per month, each with the schedule rows attached.

## Software development costs (needs a CPA policy decision — ask, don't assume)
FinVerified sells SaaS, so its platform is internal-use software (ASC 350-40). Some development costs may be capitalized instead of expensed. Prepare both versions for the CPA: (a) all expensed, (b) capitalization under ASC 350-40, including whether to early-adopt ASU 2025-06. Recommend one with your reason.

## Month-end close checklist (5th of each month)
Bank rec (Mercury) · Stripe payouts vs. revenue and fees · AP aging · accruals (Mango week split across months, Manatt) · prepaid/retainer (Manatt trust retainer is a prepaid asset, not an expense, until applied) · founder loan balance · draft journals · flux review (anything ±20% month over month explained).
