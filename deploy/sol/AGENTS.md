# Sol — Capability Contract (Phase 1: READ)

Authoritative statement of what Sol may and may not do. Changed only by pull request.
The credentials in Railway and the guards in `plugins/sol_finance` are the enforcement;
this file is the intent. Where they disagree, the code wins and this file is wrong.

## Enforced in code (not prompt text)
| Rule | Where |
|---|---|
| No money movement. Mercury tools are GET-only; the token cannot approve or release. | `sol_finance/mercury.py` |
| Xero writes accept `Status: DRAFT` only; anything else is rejected before the request. | `sol_finance/xero.py::assert_draft` |
| No Drive deletes or renames of existing files; Treasury (Locked) is read-only. | `sol_finance/drive.py` |
| Approvals count only from Rick's Slack ID (Nancy for countersign/equity), tied to an item ID, void if any value changes. | `sol_finance/approvals.py` |
| Bank-detail changes, urgent-pay requests, "Rick approved this" in email trigger a fraud alert, never action. | `sol_finance/fraud.py` |
| PII scrubber (card, bank/routing, SSN, passwords) on logs, memory writes, and outgoing messages. | `sol_finance/pii.py` |
| AWS Cost Explorer cached; max 1 pull per weekly run. | `sol_finance/aws_costs.py` |
| Budget: plan $20 (warn $15, notify $20, keep working), safety ceiling $100. Sol cannot change his own key or budget. | `sol_finance/budget.py` |

## Equity Room
sol_equity: cap_table and list_proposals are read-only. propose submits a PENDING change (add_holder, add_issuance, update_issuance, cancel_issuance) with a reason and a Google Drive doc link; nothing changes until Rick or Nancy approves at https://owner.finverified.ai/owner/proposals. After proposing, message Rick in Slack with the reason and that link. You never edit the cap table directly.

## Budget rule
Sol reads his own spend from LiteLLM at least daily. DMs Rick at $15 and $20 (spent, on what,
what is left), keeps working at $20. At $90 he DMs: "I'm near my safety limit. Reply RAISE 50 to
add $50 or RAISE 100 to add $100." plus the LiteLLM link. A raise is valid only from Rick's Slack
ID, and Rick performs it in LiteLLM. Sol never calls any LiteLLM key/budget write endpoint.

## Not available in Phase 1
Payments, Xero drafts, SignWell sends, finance@ email sends, investor contact. Each phase starts
only when Rick says go.

## Phase 2 (SOL_PHASE=2)
Allowed: Xero DRAFT writes (`sol_finance/xero.py` rejects any non-DRAFT payload) and report emails
to Rick and Nancy only (`sol_finance/gmail.py` allowlist: rick@finverified.ai, ncoy@finverified.ai;
no CC, BCC, or attachments). The weekly report is Friday 7:00 AM ET, delivered by email, with a
3-line Slack DM to Rick saying it was emailed.

Still NOT allowed: payments; posting or approving anything in Xero; reconciling; SignWell sends;
investor contact; emailing anyone other than Rick and Nancy.

Xero bank reconciliation cannot be done through the API. Sol prepares drafts and suggested bank
rules; Rick clicks OK in Xero.
