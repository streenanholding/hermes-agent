---
name: sol-vendors-billing
description: Vendor hub: vendor register, invoice filing from sol@finverified.ai, usage APIs, monthly optimization. Use for vendor, invoice, and cost questions.
---

# Skill: Vendors, billing, and cost optimization

## Connections (read-only)
| Vendor | How Sol sees it |
|---|---|
| Mercury | API read token (`MERCURY_READ_TOKEN`) |
| Stripe | Restricted read key (`STRIPE_SOL_READ_KEY`) |
| Xero | OAuth app (`XERO_CLIENT_ID/SECRET`), read + drafts |
| AWS | IAM user `sol-billing-read` (`AWSBillingReadOnlyAccess`). Cost Explorer costs $0.01 per request, so pull at most once per weekly run. |
| Anthropic / Claude | Invoices forwarded to sol@finverified.ai (Gmail filter on rick@) |
| Railway, Better Stack, Google Workspace, Linear, GitHub, Slack, Dynadot, CodeRabbit, others | Invoices forwarded to sol@finverified.ai |

## Vendor Register (Google Sheet in FinVerified Finance)
vendor | purpose | owner | plan | monthly cost | billing cycle | card (last 4) | renewal date | cancel-by date | contract link | login owner | last reviewed | keep/cut/downgrade recommendation.

## Optimization rules
- Every vendor is paid from a company card, ideally one Mercury virtual card per vendor with a monthly limit. Flag any vendor still on Rick's personal card.
- Budget alerts: AWS Budgets set (alert at 80% and 100%). Anthropic extra-usage auto-recharge must have a monthly cap.
- Flag: unused tools (no login/usage 30+ days), duplicate tools, auto-recharge patterns, failed payments, price increases, renewals within 45 days.
- Legacy vendors (AWS, Mango IT, Stripe, Better Stack, Railway) need no diligence; cost optimization only.
- Known item: Anthropic "Auto recharge extra usage, Team plan" fired roughly 200 times between January and October 2026, with failed charges on Sept 20 and Sept 22. Report the monthly trend and recommend a cap.
- Known item: Sentry is planned for cancellation in favor of Better Stack. Before cancelling, confirm the app's error reporting has been switched to Better Stack (the app's Sentry DSN env var), then recommend the cancel to Rick.
