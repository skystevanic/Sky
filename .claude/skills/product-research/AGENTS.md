# Product Research — instructions for Codex (and any agent that reads AGENTS.md)

This folder is a ready-made product research process. The full run book is in `SKILL.md` in this folder. Read it and follow it exactly; it covers first-time setup (beginner mode), the run itself, the hard rules, and the report.

Quick orientation:

- Scripts live in `scripts/` and need only Python 3.9+. Run them from this folder: `python3 scripts/check_setup.py` first.
- Two services are required: SerpApi (free plan is enough) and Apify (cents per product). The person signs up themselves and saves each code where the scripts look (Mac Keychain labels `serpapi-api-key` and `apify-api-token`, or `~/.product-research/config.json`). Never ask them to paste a code into the chat. Start every first session with Part A of SKILL.md: what the skill does, what it needs, how to get each code.
- Output is `report.pdf` built by `scripts/build_report.py` from a `report.json` shaped like `examples/sample-run/report.json`. Build with `--full`. The report is for the member: no notes about tools, costs or how it was made.
- Talk to the person in plain English, one step at a time. They may never have used a coding tool before.
