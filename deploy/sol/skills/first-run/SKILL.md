---
name: sol-first-run
description: Sol's one-time first run (FIN-954). Use when Rick says "start first run" or "run the first run". Builds the Drive folder map, Vendor Register, Founder-Paid Expense Schedule 2026, and the AWS cost-by-month table, then DMs Rick a summary with links.
---

# First run (manual trigger, once)

Max 8 tool calls per step. Scripts first. Drafts and read-only only. Never delete or rename Rick's files.

1. **Drive folder map.** `sol_drive shared_drives`, then `list` the FinVerified Finance root and **Payments Jan-Sept 2026**. Create any missing standard folders with `create_folder` (00 Inbox / Founder-Paid (Rick), Vendors, Invoices, Close, Tax, Reports). Read Treasury (Locked) names only; never copy wire details out of it.
2. **AWS cost by month, Jan 1 to today.** `sol_aws cost_by_month` (cached; one live pull per week). Put the monthly totals and top services in the Vendor Register. Known so far: about $426 total Jan to Oct 5, 2026, with Mar $12.16 and roughly $73 per month since May.
3. **Vendor Register** (Sheet via `create_sheet`): vendor | what it is for | owner | plan/tier | monthly cost | billing cycle | renewal date | cancel-by date | contract link | login owner | last reviewed. Seed it with the legacy vendors (AWS, Mango IT, Stripe, Better Stack, Railway; optimization only, no diligence), plus Anthropic, Sentry (planned cancel), and every vendor found in the statements.
4. **Founder-Paid Expense Schedule 2026** (Sheet) from **Payments Jan-Sept 2026**, following the controller-cpa skill: date | vendor | description | amount | account | bucket (A/B/?) | receipt link | paid-by (card last 4) | R&D flag | confidence | Rick to confirm. Anything unclear goes in "Rick to confirm". Do not guess.
5. **DM Rick** (`sol_dm_rick`): three-line answer first, then links to each Sheet and folder, open items, and what you need from him. Include the AI spend line from `sol_budget status`.
