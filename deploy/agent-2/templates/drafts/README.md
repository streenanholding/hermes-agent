# Approved draft templates

A draft is a copy of one of these files written to `/opt/data/drafts/pending/<date>-<tracker-slug>-<template>.md`
with every `{{...}}` filled. `draft_check.py` requires:

- front matter `template`, `kind`, `tracker` (path under `/opt/data/trackers/`)
- every `## ` heading in the template
- every line under a fact section (`What we know`, `Facts used`, `Provider facts`,
  `Requirements`, `Costs`) tagged `[S#]`, or written `NOT CONFIRMED`
- every `[S#]` defined under `## Sources` as a URL or `tracker:<path>`
- no prohibited claims (`quality/prohibited-claims.txt`), no patient or bank data

Only drafts that pass are posted to Slack. A human sends.
