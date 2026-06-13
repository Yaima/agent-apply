# Quickstart — for people who don't live in a terminal

This tool fills out job applications for you from a spreadsheet of openings.
You review everything; nothing is submitted unless you turn on live mode.
Total setup: ~20 minutes, once.

## What you need
- A Mac (Windows works too; commands differ slightly — ask any AI assistant to translate)
- Python 3.11 or newer: download from python.org → Downloads → install like any app
- An Anthropic API key (console.anthropic.com → API Keys) — lets the tool match roles to
  your résumé and answer written questions like "Why this company?" in YOUR words.
  Everything still works without it (simpler keyword matching instead)
- Your resume as a PDF

## One-time setup (copy-paste each line into Terminal, press Enter, wait)
Open Terminal (Mac: press Cmd+Space, type "terminal", Enter). Then:

    cd ~/Downloads/agent-apply        # or wherever you unzipped this folder
    python3 -m pip install -r requirements.txt
    python3 -m playwright install chromium

If you see "pip: command not found", run:  python3 -m ensurepip --upgrade  and retry.

## Tell it who you are
1. In the agent-apply folder, copy `profile.example.yaml`, rename the copy `profile.yaml`.
2. Open it in any text editor (TextEdit works — use plain text mode).
3. Replace every TODO with your real info. Rules of thumb:
   - Keep the exact spacing/indentation you see. Spaces only, never Tab.
   - If an answer contains a colon ( : ), wrap the whole answer in "double quotes".
   - Anything you leave as `null` will be answered "decline to self-identify" on
     forms, or skipped. The tool NEVER guesses demographics, salary, or visa status.
4. Put your resume PDF in the `resume/` folder and set `resume_path` to its name.

## Starting from zero — no spreadsheet yet?
You don't need one. Name a file that doesn't exist and list any companies you'd want —
startups *and* big names (Google, Apple, NVIDIA and thousands of others are found
automatically):

    python3 discover.py --tracker MyJobs.xlsx --companies "figma, google, nvidia, stripe"

It creates the spreadsheet, filled with their current openings that fit you. "Fit" comes
from your `search:` block in profile.yaml — your `roles` (e.g. `[product designer, ux
designer]`) and a `near` area (e.g. `San Francisco Bay Area`). With an Anthropic API key,
the tool reads your **résumé + profile** and keeps only roles that genuinely match and are
**commutable** (Remote always kept; far metros dropped). Override per run with `--search`,
`--near "New York"`, or `--relocate`. Then `python3 run.py` works on it like any tracker.

A few companies (Salesforce and similar) hide their listings behind bot-protection — the
tool says so and you add those by URL (see below). Want a bigger starting list? Ask Claude
to research openings for your roles, seniority, and location, then paste the URLs in.

## Try it (nothing gets submitted)
    python3 run.py

It finds your spreadsheet, checks which jobs are still open, fills each form, and
saves a screenshot in the `logs/` folder. Open a few screenshots — that's exactly
what would be sent. Jobs it can't handle go to the "Exceptions" tab of your
tracker — that's your apply-by-hand list.

## When it says "required-fields-unresolved"
That's the tool refusing to guess. Open the Exceptions tab of your tracker,
read the question it couldn't answer, then add your answer to profile.yaml:

    answers:
      custom:
        - match: part of the question text
          answer: your answer

Run it again — that question is solved forever, for every company that asks it.

## Apply for real (you press the final button, every time)
    python3 run.py --live --headed --limit 3

A browser window opens. The tool fills each form, then STOPS so you read it; fix anything
by hand, then press Enter to submit — or type `s` and Enter to skip that one. **The submit
is always yours** — there is no auto-submit, so a mistake can't go out without you seeing it. (`--live` requires
`--headed` for exactly this reason.) Apply to specific companies with
`--company google,roblox`, or leave it off to work your whole list.
When a form shows an "I'm not a robot" checkbox, click it before pressing Enter.
Some companies (those on the "Ashby" system, like OpenAI) use an invisible bot
check that rejects automated submits — the tool fills those for you but tells you
to submit them yourself in your normal browser. That's expected, not a failure. Start with 3,
check the spreadsheet and screenshots, then raise the limit.
Check two things after: the company's confirmation email arrived, and the
spreadsheet row says "Applied".

## Check your list / mark things by hand (no browser)
    python3 run.py --check                          # which postings are still live? marks dead ones "closed"
    python3 run.py --mark applied --rows 42          # you applied yourself — record it (also: closed, skip)
Both respect `--company` and `--rows` so you can scope them.

## The companies you finish by hand (Workday, Google, Apple, Ashby...)
These are *found* automatically, but you submit them yourself — some use bot checks the
tool won't try to defeat. Assist mode does the typing while you drive:

    python3 run.py --assist --headed
It opens the real job page; you log in and click "Apply", press f to fill the page,
d when you've submitted, s to skip.

## Adding a posting you found yourself (Google, Apple, anywhere)
    python3 discover.py --tracker MyJobs.xlsx --urls "PASTE_THE_JOB_URL_HERE" --company-name Google
Then work it with assist mode (above) — you sign in, the tool types.

## Find new openings at companies you care about
    python3 discover.py --tracker YOUR_SPREADSHEET.xlsx --companies "figma, roblox, notion"

New matching roles get added to your spreadsheet, ready for the next run.

## Your data stays on your machine
Your `profile.yaml`, `.env` key, trackers (`*.xlsx`), `resume/`, `logs/`, and `backups/`
are all git-ignored — if you publish or share this folder, none of your personal data
goes with it. Only the code and the blank `profile.example.yaml` template are shared.

## When something breaks
Copy the red error text and paste it to Claude (claude.ai) with "this is from the
agent-apply job tool" — the README in this folder gives it everything it needs to
help you. That's literally how this tool was built and debugged.
