"""ATS-agnostic form discovery and filling. Works on rendered DOM via Playwright."""
import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Field:
    handle: object
    kind: str            # text|email|tel|textarea|select|file|checkbox|radio-group
    label: str
    required: bool
    options: list = field(default_factory=list)
    name: str = ""

H = [  # (regex on label, profile path)
    (r"\bfirst\s*name\b", "candidate.first_name"),
    (r"\blegal name\b", "candidate.full_name"),
    (r"\blast\s*name|surname|family name\b", "candidate.last_name"),
    (r"^(full\s*)?name\b", "candidate.full_name"),
    (r"\be-?mail\b", "candidate.email"),
    (r"\bphone|mobile\b", "candidate.phone"),
    (r"\blinkedin\b", "candidate.linkedin"),
    (r"(portfolio|work samples?).{0,12}password", "candidate.portfolio_password"),
    (r"\bpronouns?\b", "candidate.pronouns"),
    (r"\bportfolio|website|personal site|url\b", "candidate.website"),
    (r"\blocation|city|where.*based|current.*residence\b", "candidate.location"),
    (r"\bcountry\b", "candidate.country"),
    (r"\bzip|postal\b", "candidate.zip"),
    (r"\b(street )?address\b", "candidate.address"),
    (r"\bcurrent (company|employer)|most recent (company|employer)\b|^company name", "work.most_recent_employer"),
    (r"\b(current |recent )?title\b", "work.current_title"),
    (r"how.*(hear|find|learn).*about", "work.how_heard"),
    (r"\bnotice period|start date|available\b|when can you start|start a new role|earliest.*start", "work.notice_period"),
    (r"(state|where).*(reside|currently live)|which (u\.?s\.? )?state", "candidate.state"),
]
SENSITIVE = [
    (r"sponsor|visa", "work.requires_sponsorship"),   # MUST precede authorization: sponsorship questions often say "work authorization"
    (r"authoriz|legally.*work|right to work", "work.work_authorization"),
    (r"salary|compensation|pay (expectation|range)", "work.salary_expectation"),
    (r"\bgender\b", "eeoc.gender"),
    (r"transgender", "eeoc.transgender"),
    (r"sexual orientation|lgbtq?", "eeoc.sexual_orientation"),
    (r"first.?generation", "eeoc.first_generation"),
    (r"hispanic|latin", "eeoc.hispanic_latino"),
    (r"race|ethnic", "eeoc.race_ethnicity"),
    (r"veteran", "eeoc.veteran_status"),
    (r"disab", "eeoc.disability_status"),
    (r"18\+|over (the age of )?18|at least 18 years", "candidate.over_18"),
    (r"^i identify\b|^do you identify\b", "eeoc.self_id_misc"),  # catch-all: must stay last
]
DECLINE_RX = re.compile(r"decline|prefer not|don[’']?t wish|do not wish|i don'?t", re.I)

def get(profile: dict, path: str):
    cur = profile
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur: return None
        cur = cur[p]
    return cur


from pathlib import Path
_SNAP = Path(__file__).with_name("snapshot.js").read_text()
_RETAG = Path(__file__).with_name("retag.js").read_text()

def _mk(page, d):
    f = Field(page.locator(f'[data-aa="{d["aa"]}"]'), d["kind"], d["label"], d["required"],
              [(t, v) for t, v in d["options"]], d.get("name", ""))
    f.page, f.aa = page, d["aa"]
    if d["kind"] == "radio-group":
        f.options = [(t, page.locator(f'[data-aa="{aa}"]')) for t, aa in d["options"]]
    return f

async def discover(page) -> list[Field]:
    data = await page.evaluate(_SNAP)
    return [_mk(page, d) for d in data]

async def retag(f: Field):
    aa = await f.page.evaluate(_RETAG, [f.label, f.kind])
    if aa is None: return False
    f.aa, f.handle = aa, f.page.locator(f'[data-aa="{aa}"]')
    return True


CONSENT_RX = re.compile(r"acknowledge|privacy (notice|policy)|terms|consent to", re.I)
ACCEPT_RX = re.compile(r"acknowledge|agree|accept|consent|^yes\b|i have read", re.I)

def map_field(f: Field, profile: dict):
    """Returns (value, source) or (None, None). source: 'profile'|'sensitive'|'decline'."""
    lab = f.label.lower()
    if CONSENT_RX.search(lab) and f.options:
        for text, _ in f.options:
            if ACCEPT_RX.search(text): return (text, "profile")
    if CONSENT_RX.search(lab) and f.kind == "text":
        return ("acknowledge", "sensitive")  # combobox acknowledgments: pick the accept option
    for rx, path in SENSITIVE:
        if re.search(rx, lab):
            v = get(profile, path)
            if v is None and f.options:
                for text, opt in f.options:
                    if DECLINE_RX.search(text): return (text, "decline")
            if v is None: return (None, "sensitive-missing")
            if isinstance(v, bool): v = "Yes" if v else "No"
            return (v, "sensitive")
    if f.kind == "checkbox":
        if re.search(r"i agree|certify|acknowledge|consent|i confirm", lab):
            return ("Yes", "profile")
        hh = get(profile, "work.how_heard") or []
        hh = hh if isinstance(hh, list) else [hh]
        if any(h.lower() == lab.strip().lower() for h in hh):
            return ("Yes", "profile")
        return (None, None)
    for entry in (get(profile, "answers.custom") or []):
        try:
            if re.search(entry.get("match", ""), lab, re.I):
                return (str(entry.get("answer", "")), "profile")
        except re.error:
            if entry.get("match", "").lower() in lab:
                return (str(entry.get("answer", "")), "profile")
    for rx, path in H:
        if re.search(rx, lab):
            v = get(profile, path)
            if v: return (str(v), "profile")
    if f.kind == "file" and (re.search(r"resume|cv", lab) or not lab):
        p = get(profile, "candidate.resume_path")
        return (p, "profile") if p and Path(p).exists() else (None, "file-missing")
    if f.kind == "file" and re.search(r"cover", lab):
        p = get(profile, "candidate.cover_letter_path")
        return (p, "profile") if p and Path(p).exists() else (None, "file-missing")
    return (None, None)

async def pick_combobox_option(f, rx):
    """Open a custom combobox (react-select style) and click the option matching rx."""
    try:
        pg = f.page
        await pg.keyboard.press("Escape")
        await f.handle.scroll_into_view_if_needed()
        await f.handle.click(timeout=5000)
        await pg.wait_for_timeout(700)
        ctrl = await f.handle.get_attribute("aria-controls")
        opts = pg.locator(f'#{ctrl} [role=option]') if ctrl else pg.locator('[role=option]:visible')
        if ctrl and not await opts.count():
            opts = pg.locator('[role=option]:visible')
        n = await opts.count()
        for i in range(n):
            t = (await opts.nth(i).inner_text()).strip()
            if rx.search(t):
                await opts.nth(i).click(timeout=5000); return t
        import sys; texts=[(await opts.nth(i).inner_text()).strip()[:45] for i in range(n)]; print(f"    pick: no match among {n} options for {f.label[:45]!r}: {texts}", file=sys.stderr)
        await pg.keyboard.press("Escape")
    except Exception as e:
        import sys; print(f"    pick error on {f.label[:50]!r}: {e!r}"[:160], file=sys.stderr)
        raise
    return None

import re as _re
def sensitive_rx(value):
    v = str(value).strip().lower()
    if "hispanic" in v: return _re.compile(r"hispanic|latin[oax]", _re.I)
    if v == "acknowledge": return ACCEPT_RX
    if _re.match(r"yes\b", v): return _re.compile(r"^\s*yes\b", _re.I)
    if _re.match(r"no\b", v):  return _re.compile(r"^\s*no\b(?!ne)", _re.I)
    if v == "male":   return _re.compile(r"^\s*(male|man)\b", _re.I)
    if v == "female": return _re.compile(r"^\s*(female|woman)\b", _re.I)
    return value_rx(value)

def value_rx(value):
    words = [w for w in re.findall(r"[a-zA-Z]{3,}", str(value))][:4]
    return re.compile("(?=.*" + ")(?=.*".join(map(re.escape, words)) + ")", re.I | re.S) if words else re.compile(re.escape(str(value)), re.I)

async def fill_field(f: Field, value):
    if f.kind == "file":
        await f.handle.set_input_files(value); return
    if f.kind == "select":
        for text, val in f.options:
            if str(value).lower() in text.lower() or text.lower() in str(value).lower():
                await f.handle.select_option(value=val); return
        raise ValueError(f"no select option matched {value!r} for {f.label!r}")
    if f.kind == "radio-group":
        for text, opt in f.options:
            if str(value).lower() in text.lower():
                await opt.check(); return
        raise ValueError(f"no radio matched {value!r} for {f.label!r}")
    if f.kind == "checkbox":
        if str(value).lower() in ("yes", "true", "1"):
            await f.handle.check()
            if not await f.handle.evaluate("e=>e.checked"):
                raise ValueError(f"checkbox did not register: {f.label!r}")
        return
    await f.handle.fill(str(value))
    combo = await f.handle.evaluate("""e=>e.getAttribute('aria-autocomplete')==='list'||e.getAttribute('role')==='combobox'||!!e.closest('[role=combobox]')""")
    if combo:
        pg = f.handle.page
        await pg.keyboard.press("Escape")
        await f.handle.click(timeout=5000)
        await pg.wait_for_timeout(500)

        async def options():
            ctrl = await f.handle.get_attribute("aria-controls")
            o = pg.locator(f'#{ctrl} [role=option]') if ctrl else pg.locator('[role=option]:visible')
            if ctrl and not await o.count():
                o = pg.locator('[role=option]:visible')
            return o

        o = await options()
        if not await o.count():  # type-ahead widget: real keystrokes, short query
            await f.handle.fill("")
            await pg.keyboard.type(" ".join(str(value).split()[:2]), delay=50)
            await pg.wait_for_timeout(1600)
            o = await options()
        n, rx, pick = await o.count(), value_rx(value), None
        for i in range(min(n, 60)):
            if rx.search((await o.nth(i).inner_text()).strip()):
                pick = o.nth(i); break
        if pick is None and n:
            pick = o.first  # nothing ranks: take the top suggestion
        if pick is None:
            await f.handle.fill(str(value))   # no suggestion list: treat as plain text input
            return
        await pick.click(timeout=5000)
        await pg.keyboard.press("Escape")
        return
