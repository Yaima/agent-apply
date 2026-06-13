# agent-apply — auto-apply agent for a job tracker spreadsheet

Reads a tracker spreadsheet of job postings, verifies each is still live, fills the
application from `profile.yaml` (+ your resume PDF), and — in live mode — submits.
Results write back into the **same tracker** (a timestamped snapshot is saved under
`backups/` first); anything needing a human lands in an **Exceptions** tab. Every attempt
produces a full-page screenshot and a `_result.json` in `logs/` so you can audit exactly
what went out.

Built for one job search; written to be reusable for anyone's. Pair it with an
AI-assisted tracker build (any spreadsheet matching the schema below works).

## Code map
```
discover.py       company name → source resolver + role fetchers (Greenhouse/Ashby/Lever
                  boards, Google, Apple, Workday) + --careers-url + dedupe/append
run.py            apply loop: liveness → classify ATS → fill → human-reviewed submit.
                  Also --check (liveness sweep) and --mark (manual status), no browser
agent/ats.py      ATS detection from URL/HTML; AUTOMATABLE and RECAPTCHA_V3 sets
agent/forms/      snapshot.js/retag.js discover form fields; common.py maps fields ↔ profile
                  (sensitive fields never guessed); apply.py runs the fill+submit flow
agent/llm.py      Claude helpers: résumé-aware role ranking + free-text answers,
                  key-gated with graceful keyword fallback
agent/tracker.py  the .xlsx read/write, status marks, and backups/
profile.yaml      who you are (gitignored); profile.example.yaml is the template
```

## The process, end to end
1. Fill `profile.yaml` (copy from `profile.example.yaml`); put your resume PDF in `resume/`.
2. Get a tracker: bring your own spreadsheet matching the schema below, or bootstrap
   one with `discover.py` (creates the file if it doesn't exist).
3. Dry run (`python run.py`). Nothing submits. Read `logs/` screenshots and the
   Exceptions tab of your tracker.
4. Triage loop: every "required-fields-unresolved" question becomes a two-line
   `answers.custom` entry (or a profile field). Re-run; exceptions shrink.
5. Pilot live: `--live --headed --limit 3`. The tool fills each form, then pauses —
   inspect it, fix anything by hand, press Enter to submit (or `s` to skip). Verify the
   confirmation emails arrive and the tracker shows "Applied".
6. Scale: raise `--limit`; target with `--company` / `--rows`; refresh roles with
   `discover.py`. The submit is always yours — there is no unattended-submit mode to graduate to.
7. Work the manual tail with `--assist --headed` (Workday/Google/Apple: you log
   in and click Next, the agent types). LinkedIn and `human_only_companies`
   stay fully by-hand, on purpose.
8. The Exceptions tab is the standing to-do list; the Follow-up column is yours.

## Tracker schema (sheet must be named "Job Tracker")
Columns by position: A `#`, B `Company`, C `Role`, D `Level`, E `Address`, F `City`,
G `Mode`, H `Approx Mi`, I `Caltrain`, J `Salary`, **K `Application URL`**, L `Notes`,
M `Status`, N `Applied?`, O `Date`, P `Follow-up`. The agent reads K, writes M–P.
Rows with anything in `Applied?` are never re-attempted.

## Setup
    pip install -r requirements.txt
    python -m playwright install chromium
    export ANTHROPIC_API_KEY=...        # résumé-aware matching (--match llm), --near, free-text answers

Copy `profile.example.yaml` → `profile.yaml` and fill it in. Hard rules the agent
enforces, in your favor:
- EEO/demographics, work authorization, sponsorship, salary come ONLY from the
  profile. Missing → the form's "decline to self-identify" option; no decline
  option → Exceptions. The LLM never guesses these, and never invents employers,
  dates, or facts.
- `start_in_days: 14` computes "available from <date>" at run time — no stale dates.
- `answers.custom` is a no-code answer map: when a run reports an unresolved
  question, add `{match: "phrase from the question", answer: "..."}` and re-run.
- `human_only_companies` routes listed companies (Anthropic ships in the default —
  their posted policy asks candidates not to use AI on applications) entirely to
  the Exceptions tab; a page-text detector catches other companies' AI policies.
- Dry-run is the default. `--live` refuses to start while the profile has TODOs,
  and `policy.max_per_run` caps submissions per invocation.

## Targeting & discovery
    python discover.py --tracker YourTracker.xlsx --companies "roblox, figma, sony, google, nvidia"
If the tracker file doesn't exist yet, it is created with the correct schema — discovery
doubles as the from-zero bootstrap. For each company it resolves the right source
automatically, pulls open roles, keeps the ones that fit you, dedupes against the tracker,
and appends them as agent-ready rows.

**Where roles come from, by company (resolved automatically from the name):**
- **Greenhouse / Ashby / Lever** — public board APIs (figma, roblox, stripe, …).
- **Google** — `careers.google.com` (server-rendered, query-filtered).
- **Apple** — `jobs.apple.com` keyword search.
- **Workday** (NVIDIA, Cisco, and thousands more) — public JSON API. Resolved from a small
  built-in registry, else a best-effort tenant probe. If the probe misses, pass the URL:
      python discover.py --tracker YourTracker.xlsx --careers-url "https://<tenant>.wd5.myworkdayjobs.com/<Site>" --company-name Adobe
  `--careers-url` is the reliable universal path for any supported ATS — paste a company's
  Workday / Greenhouse / Lever / Ashby / Google / Apple careers URL and it pulls all roles.

**Scope the search** with `--search "ux designer, design systems"` (a comma list of roles,
each searched and unioned; defaults to your `search.roles`), `--location` (default
"united states"), and `--max-pages` (default 12).

**Filter by commute** with `--near` (LLM matching only) — keep only roles within commuting
range of an area you name; Remote is always kept, far metros (e.g. NYC) dropped. Add
`--relocate` to also keep strong out-of-area roles as relocation options:
    python discover.py --tracker YourTracker.xlsx --companies "google, nvidia" \
        --search "ux designer, design systems" --near "San Francisco Bay Area"

**Matching — `--match` (default `auto`):**
- `llm` (auto when `ANTHROPIC_API_KEY` is set) — ranks each role against your **profile +
  résumé PDF** with Claude; the kept rows note why. Truly "based on your résumé."
- `keyword` (auto when no key) — your `search:` profile (`roles`/`levels`/`exclude`, or a
  raw `title_match` regex) filters titles. Fast, free, deterministic.

**Salesforce and other JS-gated sites** run all search/filter/pagination through a
bot-guarded JavaScript API that returns the same unfiltered list to any non-interactive
request (verified, even via a real browser). They can't be auto-discovered without forging
anti-bot tokens — which this tool refuses to do — so `discover.py` says so and points you to
`--urls` for hand-picked postings:
    python discover.py --tracker YourTracker.xlsx --urls "<posting url>" --company-name Salesforce
Discovered Google/Apple/Workday rows are tagged accordingly — applied by hand / `--assist`
(custom portals, never auto-submitted). Then apply to just some companies:
    python run.py --tracker YourTracker.xlsx --company roblox --live --headed

## Run
    python run.py --tracker YourTracker.xlsx                       # dry run (fills, submits nothing)
    python run.py --tracker YourTracker.xlsx --company google,roblox  # only these companies
    python run.py --tracker YourTracker.xlsx --rows 10-40,55       # specific rows/ranges
    python run.py --tracker YourTracker.xlsx --live --headed --limit 3   # pilot
With no `--company`/`--rows`, it works every unapplied row (capped by `--limit` /
`policy.max_per_run`). **A human always confirms each submit:** `--live` requires `--headed`,
and the tool fills each form, then pauses so you inspect it (fix any field by hand) and
press Enter to submit — there is no fully-automated submit path, by design. It still pauses
for you to click any visible CAPTCHA first.

The tracker is edited **in place** (a timestamped snapshot is saved under `backups/` first).
Two no-browser helpers work on the same file, honoring `--rows`/`--company`:
    python run.py --tracker YourTracker.xlsx --check               # which postings are still live? marks closed ones
    python run.py --tracker YourTracker.xlsx --mark applied --rows 42 --note "ref #123"   # set status by hand
`--mark` takes `applied` | `closed` | `skip` | any free text. Recaptcha-v3 (Ashby) rows are
labeled "apply by hand"; in `--assist --headed` they open on the **role page** (where "Apply
now" lives) so you complete them in your own session — the agent fills, you submit.

Re-runs resume from the same tracker automatically — applied rows are skipped, so
interrupting and restarting never double-applies. In `--live --headed` mode the run
pauses at visible CAPTCHAs (new Greenhouse forms end in a reCAPTCHA checkbox): click
it in the browser, press Enter in the terminal, the agent submits and verifies. The
agent does not and will not bypass CAPTCHAs.

## Assist mode — companies that need a human anyway
    python run.py --tracker YourTracker.xlsx --assist --headed
Rows on Workday, Google Careers, Apple, and custom portals open in the visible
browser instead of going straight to Exceptions: you log in and navigate to the
form (the part automation can't do), press `f` and the agent fills the page in
front of you, you click Next and repeat, then `d` once you've submitted (marks
Applied) or `s` to skip. Two deliberate exceptions remain: LinkedIn (platform
terms prohibit automated activity even supervised) and `human_only_companies`
(Anthropic's policy covers AI-prepared content, not just submission).

## What's automated vs. not
- **Fully fillable, you submit**: Greenhouse (reCAPTCHA v2 — the visible checkbox you
  click during a run), Lever. The agent fills everything and reaches the submit button;
  you review and press Enter (or `s` to skip). Custom domains backed by these are followed.
- **Filled but NOT auto-submitted**: Ashby. Ashby uses invisible reCAPTCHA v3,
  which scores the whole browser session and flags Playwright-driven submits as
  spam. Live runs fill these for your reference and route them to Exceptions as
  "apply by hand". Submit them in your normal browser, or use `--assist` to fill
  inside your own session. (`--allow-flagged` forces a submit attempt; it will
  almost certainly be rejected — don't.)
- **Routed to Exceptions** (or handled interactively with `--assist`): Workday,
  Google Careers, Apple, aggregators — plus, always by hand: LinkedIn,
  unreachable/bot-blocked sites, dead postings, AI-policy companies, and any
  required question the profile + LLM can't answer above the confidence floor.
- Closed postings are detected by status code AND by the silent redirect-to-board
  pattern, and marked "Posting closed".

## reCAPTCHA, honestly
Greenhouse = reCAPTCHA v2: a visible checkbox. The agent pauses, you click it, it
submits. Works. Ashby = reCAPTCHA v3: invisible, scores how human the *session*
looks; an automated session fails no matter who clicks submit, and clicking by
hand inside that session doesn't rescue it. The tool will not try to defeat bot
detection — for v3 sites it fills the form as a reference and you submit yourself.
This is a deliberate limit, not a bug.

## Audit habits that kept this honest
Trust screenshots over logs until you've watched a few clean live runs. Read the
LLM-answered text in `logs/*_result.json` before scaling up — it's your voice going
out. And keep the human on the CAPTCHA click and the essay questions that deserve
a person (some companies explicitly require it; respect that).

## Note on attestations
Forms include "I certify this is accurate." The agent checks it because the
candidate authorized the run — keep the candidate in the loop via screenshots and
the updated tracker so they always know what went out under their name.

## Privacy & publishing
This repo is built to be public; your data is not. The `.gitignore` keeps everything
personal out of git: `profile.yaml` (name, address, EEO, passwords), `.env` (API key),
your trackers (`*.xlsx`), `resume/`, and run artifacts (`logs/`, `backups/`). Only the
code and the blank `profile.example.yaml` are tracked. Before pushing a fork, sanity-check
with `git status` that no `.xlsx`, `profile.yaml`, or `.env` is staged. To get a new copy
going: `cp profile.example.yaml profile.yaml`, fill it in, drop your résumé in `resume/`,
and set `ANTHROPIC_API_KEY` (in `.env` or your shell).
