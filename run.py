#!/usr/bin/env python3
"""Auto-apply agent. DRY-RUN by default; pass --live (with --headed) to submit — and a human
reviews and presses Enter for every submission. There is no fully-automated submit path.
Usage:
  python run.py --tracker YourTracker.xlsx                        # dry-run, automatable ATS only
  python run.py --tracker YourTracker.xlsx --live --headed --limit 5    # first live pilot
  python run.py --tracker YourTracker.xlsx --check                # liveness sweep only, no browser
"""
import argparse, asyncio, json, re, sys
from pathlib import Path
import httpx, yaml
from playwright.async_api import async_playwright
from agent.ats import classify, AUTOMATABLE, RECAPTCHA_V3, rewrite
from agent.tracker import Tracker, backup
from agent.forms import apply as flow

def liveness(client, url):
    try:
        r = client.get(url, follow_redirects=True, timeout=15)
        if r.status_code in (404, 410): return "closed", r
        if r.status_code >= 400: return f"http-{r.status_code}", r
        final = str(r.url)
        jid = re.search(r"/jobs?/(\d{6,})", url)
        # closed only when a job-id URL redirected to a board LISTING that dropped the id
        # (requires positive evidence of a listing path — avoids false "closed" on id rewrites)
        if jid and jid.group(1) not in final and re.search(r"/(jobs|careers|openings|positions)/?(\?|$)", final, re.I):
            return "closed", r
        # require a strong, unambiguous closed phrase (the old loose regex false-flagged live roles)
        if re.search(r"no longer accepting|no longer available|this (job|role|position|posting)[^.]{0,30}"
                     r"(closed|no longer|filled|removed)|position (has been|is) (closed|filled)|"
                     r"posting (is )?closed", r.text, re.I):
            return "closed", r
        return "live", r
    except Exception as e:
        return f"unreachable:{type(e).__name__}", None

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracker", default=None)
    ap.add_argument("--profile", default="profile.yaml")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rows", default=None, help="comma-separated Excel row numbers")
    ap.add_argument("--company", default=None, help="only rows whose Company matches (comma-separated, substring ok)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--review", action="store_true", help="(now always on in --live) the tool pauses on every filled form so you inspect it and press Enter to submit")
    ap.add_argument("--assist", action="store_true", help="with --headed: manual-ATS rows (Workday/Google/etc.) open interactively — you log in & navigate, the agent fills each page on 'f'")
    ap.add_argument("--allow-flagged", action="store_true", help="override: attempt submit even on invisible-reCAPTCHA sites (will likely be flagged as spam — not recommended)")
    ap.add_argument("--check", action="store_true", help="verify-only: report which tracked postings are still live/closed (no browser, no applying); marks closed rows")
    ap.add_argument("--mark", default=None, metavar="STATUS", help="manually set status on selected rows (use with --rows/--company): applied | closed | skip | <free text>; no browser")
    ap.add_argument("--note", default=None, help="optional note stored with --mark applied (e.g. confirmation #)")
    args = ap.parse_args()

    if not args.tracker:
        opts = sorted(p.name for p in Path(".").glob("*.xlsx") if not p.name.endswith("_updated.xlsx"))
        if not opts:
            sys.exit("No tracker spreadsheet (.xlsx) found in this folder. Put your tracker file here and run again.")
        if len(opts) == 1:
            args.tracker = opts[0]; print(f"Using tracker: {opts[0]}")
        else:
            print("Which tracker should I use?")
            for i, o in enumerate(opts, 1): print(f"  {i}. {o}")
            try:
                args.tracker = opts[int(input("Enter a number: ").strip()) - 1]
            except (ValueError, IndexError):
                sys.exit("That wasn't one of the numbers listed. Run again and pick a number from the list.")
    if not Path(args.tracker).exists():
        near = sorted(p.name for p in Path(".").glob("*.xlsx"))
        sys.exit(f"Can't find '{args.tracker}' in this folder.\nSpreadsheets that ARE here: {near or 'none'}\nTip: the file must sit in the same folder as run.py, and the name must match exactly.")
    try:
        profile = yaml.safe_load(open(args.profile))
    except FileNotFoundError:
        sys.exit("profile.yaml is missing. Copy profile.example.yaml to profile.yaml and fill it in.")
    except yaml.YAMLError as e:
        sys.exit(f"profile.yaml has a formatting problem and can't be read:\n  {e}\nCommon causes: a tab instead of spaces, or an answer containing a colon — wrap that answer in \"double quotes\".")
    days = profile.get("work", {}).get("start_in_days")
    if days and not profile["work"].get("notice_period"):
        from datetime import date as _d, timedelta as _td
        profile["work"]["notice_period"] = f"Available from {(_d.today() + _td(days=int(days))).strftime('%B %d, %Y')} ({int(days)} days' notice)"
    todos = [s for s in json.dumps(profile) .split('"') if s.startswith("TODO")]
    if args.live and todos:
        sys.exit(f"profile.yaml still has TODOs ({len(todos)}); refusing --live run.")
    if args.live and not args.headed:    # a human must watch and approve every submission
        sys.exit("--live requires --headed: the tool fills each form but a human reviews it and presses Enter to submit. Re-run with --headed.")
    Path("logs").mkdir(exist_ok=True)
    out = src = args.tracker            # one tracker: read and write the same file
    backup(src)                         # safety snapshot into backups/ before editing in place
    print(f"Working in {out} (rows already marked Applied? are skipped)")
    tr = Tracker(src, out)
    rows = list(tr.rows_to_apply())
    if args.rows:
        keep = set()
        for part in args.rows.split(","):
            a, _, b = part.partition("-")
            keep.update(range(int(a), int(b) + 1) if b else [int(a)])
        rows = [r for r in rows if r[0] in keep]
    if args.company:
        wants = [c.strip().lower() for c in args.company.split(",")]
        rows = [r for r in rows if any(w in str(r[1]).lower() for w in wants)]
    limit = args.limit or profile["policy"]["max_per_run"]
    done = 0
    ua = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    if args.mark:                        # manual status set on selected rows, no browser
        if not (args.rows or args.company):
            sys.exit("--mark needs --rows and/or --company to choose which rows to mark (refusing to mark every row).")
        kind = args.mark.strip().lower()
        for r, company, role, url in rows:
            if kind == "applied":
                tr.mark_applied(r, args.note or "marked applied by hand")
            elif kind == "closed":
                tr.mark_closed(r)
            elif kind in ("skip", "skipped", "exception"):
                tr.mark_exception(r, company, role, url, "manual", args.note or "marked by hand")
            else:
                tr.sh.cell(r, 13).value = args.mark; tr.save()   # free-text status
            print(f"row {r:>3}  {str(company)[:18]:18} -> {args.mark}")
        print(f"\n{len(rows)} row(s) marked '{args.mark}' -> {out}")
        return
    if args.check:                       # verify-only: liveness sweep, no browser, no applying
        live = closed = bad = 0
        with httpx.Client(headers=ua) as client:
            for r, company, role, url in rows:
                if not str(url).strip():
                    bad += 1; print(f"row {r:>3}  {str(company)[:18]:18} {'no-url':11} {str(role)[:42]}"); continue
                state, _ = liveness(client, rewrite(url))
                if state == "live":
                    live += 1; tag = "live"
                elif state == "closed":
                    closed += 1; tr.mark_closed(r); tag = "CLOSED"
                else:
                    bad += 1; tag = state
                print(f"row {r:>3}  {str(company)[:18]:18} {tag:11} {str(role)[:42]}")
        tr.save()
        print(f"\n{len(rows)} unapplied rows checked: {live} live, {closed} closed (marked), {bad} unreachable/no-url\n-> {out}")
        return
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        ctx = await browser.new_context(user_agent=ua["User-Agent"])
        ctx.set_default_timeout(10000)
        with httpx.Client(headers=ua) as client:
            for r, company, role, url in rows:
                if done >= limit: break
                if any(re.search(pat, str(role) or "") for pat in profile["policy"].get("skip_title_patterns", [])):
                    tr.sh.cell(r, 13).value = "Skipped (title filter)"; tr.save()
                    print(f"row {r:>3} {company} — skipped by title filter"); continue
                if any(h.lower() in str(company).lower() for h in profile["policy"].get("human_only_companies", [])):
                    tr.mark_exception(r, company, role, url, "human-only", "company policy: application must be completed without AI assistance")
                    print(f"row {r:>3} {company} — human-only per policy, routed to Exceptions"); continue
                role_url = url                       # the human-facing posting ("Apply now" lives here)
                url = rewrite(url)                   # mapped form/embed URL — for classify + automated fill
                state, resp = liveness(client, url)
                if state == "closed":
                    tr.mark_closed(r); print(f"row {r:>3} {company} — closed"); continue
                if state != "live":
                    tr.mark_exception(r, company, role, url, "unreachable", state); continue
                ats = classify(url, resp.text if resp else "", str(resp.url) if resp else "")
                v3 = ats in RECAPTCHA_V3             # invisible reCAPTCHA v3 (Ashby): never auto-submit
                if (ats not in AUTOMATABLE or v3):
                    if args.assist and args.headed and ats != "linkedin":
                        page = await ctx.new_page()
                        try:
                            # open the ROLE page, not the bare form — you click "Apply now" in your own session
                            await page.goto(role_url, wait_until="domcontentloaded", timeout=45000)
                            tag = "reCAPTCHA v3 — " if v3 else ""
                            print(f"row {r:>3} {company} — ASSIST ({tag}log in, click Apply, navigate to the form).")
                            while True:
                                cmd = (await asyncio.get_event_loop().run_in_executor(
                                    None, lambda: input("     [f] fill this page  [d] I submitted it  [s] skip row: "))).strip().lower()
                                if cmd == "f":
                                    from agent.forms import common as _c
                                    flds = await _c.discover(page)
                                    fl, un, _ = await flow.fill_fields(page, flds, profile, {"company": company, "role": role})
                                    print(f"     filled {len(fl)} field(s); needs you: {[l for l,_ in un] or 'none'}")
                                elif cmd == "d":
                                    tr.mark_applied(r, "assisted manual submit"); done += 1; break
                                elif cmd == "s":
                                    tr.mark_exception(r, company, role, url, f"manual-ats:{ats}", "skipped in assist"); break
                        finally:
                            await page.close()
                        continue
                    if ats not in AUTOMATABLE:       # true manual ATS, no assist → Exceptions
                        tr.mark_exception(r, company, role, url, f"manual-ats:{ats}",
                                          "platform prohibits automation; apply by hand" if ats == "linkedin" else "")
                        print(f"row {r:>3} {company} — {ats}, routed to Exceptions"); continue
                    # else: v3 (Ashby) without --assist → fall through to automated fill-for-reference (never submits)
                page = await ctx.new_page()
                shot = f"logs/row{r}_{company.replace(' ','_')}.png"
                async def pause(pg):
                    print(f"  >> CAPTCHA on {company}: click the checkbox in the browser window, then press Enter here.")
                    await asyncio.get_event_loop().run_in_executor(None, input)
                async def review(pg):
                    print(f"  >> REVIEW {company} — {role}: check the filled form in the browser (fix any field by hand first).")
                    ans = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("     [Enter]=submit   [s]=skip this one: "))
                    return "skip" if ans.strip().lower() in ("s", "skip", "n") else "submit"
                try:
                    res = await flow.run(page, str(resp.url), ats, profile,
                                         {"company": company, "role": role}, shot, live=args.live,
                                         pause_for_human=pause if (args.live and args.headed) else None,
                                         review_pause=review if (args.live and args.headed) else None,  # always: a human confirms every submit
                                         allow_flagged=args.allow_flagged)
                except Exception as e:
                    res = {"status": "exception", "reason": "crash", "detail": repr(e)[:200]}
                finally:
                    json.dump(res if 'res' in dir() else {}, open(shot.replace(".png", "_result.json"), "w"), default=str, indent=1)
                    await page.close()
                if res["status"] == "submitted":
                    tr.mark_applied(r, res.get("detail", "submitted")); done += 1
                elif res["status"] == "dry-run-ok":
                    tr.mark_dryrun(r)
                    print(f"row {r:>3} {company} — DRY RUN ok, {len(res['filled'])} fields, see {shot}"); done += 1
                elif res.get("reason") == "no-confirmation-after-submit":
                    # the button WAS clicked — never blind-retry; flag for the human to verify
                    tr.mark_needs_check(r, "submitted but no confirmation seen — verify by hand")
                    print(f"row {r:>3} {company} — SUBMITTED but unconfirmed; flagged for your check"); done += 1
                else:
                    tr.mark_exception(r, company, role, url, res["reason"], res.get("detail", ""))
                    print(f"row {r:>3} {company} — exception: {res['reason']}")
                print(json.dumps({k: v for k, v in res.items() if k != 'filled'})[:200])
        await browser.close()
    print(f"\nDone. Tracker written to {out}; screenshots in logs/.")

if __name__ == "__main__":
    asyncio.run(main())
