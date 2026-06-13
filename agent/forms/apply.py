"""Generic application flow used for greenhouse/lever/ashby (rendered-DOM driven)."""
import re
from agent.forms import common
from agent import llm

INVISIBLE_CAPTCHA_ATS = {"ashby"}
SUBMIT_RX = re.compile(r"submit application|submit|apply now|send application", re.I)
CONFIRM_RX = re.compile(r"thank you|application (was )?(submitted|received)|we('| ha)ve received", re.I)

async def goto_application(page, url, ats):
    if ats == "ashby" and "ashbyhq.com" in url and not url.rstrip("/").endswith("/application"):
        url = url.rstrip("/") + "/application"
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(2500)
    # Lever and many Greenhouse pages need a click-through to the form
    for sel in ('a:has-text("Apply for this job")', 'a:has-text("Apply")',
                'button:has-text("Apply")', '[data-qa="btn-apply"]'):
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible():
                await loc.click(); await page.wait_for_timeout(2500); break
        except Exception:
            pass

async def detect_blockers(page):
    cap = page.locator('iframe[src*="recaptcha"]:visible, iframe[src*="hcaptcha"]:visible, .h-captcha:visible, .g-recaptcha:visible')
    for i in range(await cap.count()):
        box = await cap.nth(i).bounding_box()
        if box and box["width"] > 10 and box["height"] > 10:
            return "captcha-challenge"
    if re.search(r"sign in|log in to apply|create.*account", (await page.title()).lower()):
        return "login-wall"
    return None

async def fill_fields(page, fields, profile, job):
    filled, unmapped, min_conf, seen = [], [], 1.0, set()
    for f in fields:
        if (f.label, f.kind) in seen: continue
        seen.add((f.label, f.kind))
        value, source = common.map_field(f, profile)
        async def with_retry(op, fld):
            try:
                return await op(fld), fld
            except Exception:
                if not await common.retag(fld): raise
                return await op(fld), fld
        if source == "file-missing":
            if f.required:
                unmapped.append((f.label, "needs human: required file (résumé/cover letter) — check candidate.resume_path points to an existing file"))
            continue
        if source == "sensitive-missing":
            chosen, f = (await with_retry(lambda g: common.pick_combobox_option(g, common.DECLINE_RX), f)) if f.kind in ("text","select") else (None, f)
            if chosen:
                filled.append((f.label, f"decline:{chosen[:40]}")); continue
            if f.required:
                unmapped.append((f.label, "needs human: demographic/legal field with no decline option or profile value"))
            continue
        if f.kind == "checkbox" and value is None:
            continue  # option-style checkboxes (e.g. 'how did you hear') are never individually required
        if value is None and source is None and f.required:
            r = llm.answer_question(f.label, f.kind, f.options, profile, job)
            if r.get("answer") and r.get("confidence", 0) >= profile["policy"]["min_confidence"]:
                value, source, min_conf = r["answer"], "llm", min(min_conf, r["confidence"])
            else:
                unmapped.append((f.label, r.get("reason", "no mapping")))
                continue
        if value is None:
            continue
        try:
            if source in ("sensitive", "llm") and f.kind == "text":
                vals = value if isinstance(value, list) else [value]
                got = []
                for v in vals:
                    rx = common.sensitive_rx(v) if source == "sensitive" else common.value_rx(v)
                    chosen, f = await with_retry(lambda g: common.pick_combobox_option(g, rx), f)
                    if chosen: got.append(chosen)
                if got:
                    filled.append((f.label, f"{source}:{','.join(t[:25] for t in got)}")); continue
            _, f = await with_retry(lambda g: common.fill_field(g, value), f)
            filled.append((f.label, source))
        except Exception as e:
            if f.required:
                unmapped.append((f.label, f"fill-error: {repr(e)[:120]}"))
    return filled, unmapped, min_conf

async def run(page, url, ats, profile, job, screenshot_path, live=False, pause_for_human=None, review_pause=None, allow_flagged=False):
    """Returns dict(status='submitted'|'dry-run-ok'|'exception', reason, detail, filled, unmapped)."""
    await goto_application(page, url, ats)
    body = await page.content()
    if re.search(r"sign in to apply|log in to apply", body[:5000], re.I):
        return {"status": "exception", "reason": "login-wall", "detail": page.url}
    if re.search(r"candidates.{0,4}AI usage|policy for using AI in (our|the) application|do not use AI assist|without (the use of|using) AI (assistants|tools)", body, re.I):
        return {"status": "exception", "reason": "ai-policy-human-required",
                "detail": "posting declares an AI-usage policy for applications; complete by hand"}
    fields = await common.discover(page)
    if not any(f.kind == "file" for f in fields) and not any("email" in f.label.lower() for f in fields):
        # custom-domain sites often embed the real form in a Greenhouse/Ashby iframe — follow it
        src = await page.evaluate("""()=>{const f=document.querySelector('iframe[src*="greenhouse"],iframe[src*="ashbyhq"],#grnhse_iframe');return f?f.src:null}""")
        if src:
            await page.goto(src, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            fields = await common.discover(page)
        if not any(f.kind == "file" for f in fields) and not any("email" in f.label.lower() for f in fields):
            return {"status": "exception", "reason": "no-application-form", "detail": f"{len(fields)} fields found"}
    filled, unmapped, min_conf = await fill_fields(page, fields, profile, job)
    await page.screenshot(path=screenshot_path, full_page=True)
    if unmapped:
        return {"status": "exception", "reason": "required-fields-unresolved",
                "detail": "; ".join(l for l, _ in unmapped[:5]), "filled": filled, "unmapped": unmapped}
    if not live:
        return {"status": "dry-run-ok", "filled": filled, "unmapped": [], "confidence": min_conf}
    # LIVE — a human must authorize every submit; there is no autonomous submit path.
    if review_pause is None:
        return {"status": "exception", "reason": "no-human-review",
                "detail": "refusing to submit without a human reviewer (--live requires --headed)", "filled": filled}
    if ats in INVISIBLE_CAPTCHA_ATS and not allow_flagged:
        return {"status": "exception", "reason": "recaptcha-v3-apply-by-hand", "filled": filled,
                "detail": f"{ats} uses invisible reCAPTCHA v3, which scores the whole browser session; "
                          "automated submits get flagged as spam. The form was filled for your reference — "
                          "apply by hand in your normal browser, or use --assist to fill it inside your own session."}
    blocker = await detect_blockers(page)
    if blocker == "captcha-challenge":
        if pause_for_human:
            await pause_for_human(page)   # human clicks the checkbox, then we continue
        else:
            return {"status": "exception", "reason": "captcha-needs-human", "detail": page.url,
                    "filled": filled}
    btn = page.locator("button:visible, input[type=submit]:visible").filter(has_text=SUBMIT_RX).first
    if not await btn.count():
        return {"status": "exception", "reason": "no-submit-button", "detail": "", "filled": filled}
    # Final, authoritative human gate: the reviewer decides submit vs skip. Nothing is
    # clicked until they choose "submit". (review_pause returns "submit" | "skip".)
    if await review_pause(page) == "skip":
        return {"status": "exception", "reason": "human-skipped", "filled": filled,
                "detail": "you chose not to submit this one"}
    await btn.click()
    try:
        await page.wait_for_function(
            """rx => new RegExp(rx, 'i').test(document.body.innerText)""",
            arg=CONFIRM_RX.pattern, timeout=20000)
        await page.screenshot(path=screenshot_path.replace(".png", "_confirm.png"), full_page=True)
        return {"status": "submitted", "filled": filled, "confidence": min_conf,
                "detail": "confirmation text detected"}
    except Exception:
        return {"status": "exception", "reason": "no-confirmation-after-submit", "detail": page.url}
