---
name: carol-first-run
description: Carol's one-time setup. Use when Rick says "start first run". Creates her working folders and vendor trackers, finds named contacts for every RFP vendor, sets her schedules, and sends Rick a one-screen summary.
version: 1.0.0
---

# First run (once, when Rick says "start first run")

Keep each step short. Drafts only. No PHI. Cite every source URL.

1. **Folders.** Create `/opt/data/payverified/` with `vendors/`, `payers/`, `enrollments/`,
   `costs/`, `rfp/`. If `vendors/` is empty, copy each file from
   `/opt/data/templates/vendors/` into it. Never overwrite a tracker that already exists.
2. **Contacts.** For each vendor tracker, use web search to find the best person or channel
   for a partnership/enterprise price quote: name, title, email if publicly listed, phone,
   and the official sales or partner form URL. Prefer the vendor's own site. Never guess an
   email from a pattern; if no email is published, record the form URL and phone and mark
   the email NOT CONFIRMED. Save in each tracker under "Contacts".
3. **Pre-score.** Score each vendor with the `vendor-scoring` skill from public information
   only, mark it "pre-RFP", and list the questions that would change the score most.
4. **Payer map seed.** Create payer files for: Medicare (HETS + First Coast for Florida),
   Florida Medicaid and its dental plans, the national commercial carriers, the top dental
   carriers. Fill only confirmed facts with sources.
5. **Schedules.** With `cronjob`, create the four schedules in AGENTS.md (weekday stale
   check, Monday update, monthly cost report, quarterly market check). Skip any that
   already exist.
6. **Tell Rick** in one message: what you set up, the contact table (vendor | person |
   email or form | phone | confirmed?), the pre-RFP ranking in one line each, and the
   three things you need from him.
