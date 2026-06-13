"""Claude API helpers: answer custom questions, choose options, score confidence.
Degrades gracefully when ANTHROPIC_API_KEY is absent (heuristics-only mode)."""
import base64, json, os
from pathlib import Path

MODEL = "claude-sonnet-4-6"
_client = None
_brief = None  # cached candidate brief for a discovery run

def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))

def _cl():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client

def answer_question(question: str, kind: str, options: list, profile: dict, job: dict):
    """Returns dict {answer, confidence, reason}. Never invents facts not in profile."""
    if not available():
        return {"answer": None, "confidence": 0.0, "reason": "no API key"}
    ctx = {
        "candidate": {k: v for k, v in profile.get("candidate", {}).items() if "path" not in k},
        "work": profile.get("work", {}),
        "canned_answers": profile.get("answers", {}),
        "job": job,
    }
    opts = f"\nOptions (must pick exactly one): {[o for o, _ in options]}" if options else ""
    msg = _cl().messages.create(
        model=MODEL, max_tokens=600,
        system=(
            "You fill job application fields for a candidate using ONLY the provided profile. "
            "Rules: never invent employers, dates, degrees, demographics, salary, or legal status; "
            "if the profile lacks the needed fact, return confidence 0. Short fields get short answers; "
            "free-text questions get 2-4 specific sentences in first person, plain tone, no buzzwords. "
            'Respond ONLY with JSON: {"answer": str, "confidence": 0-1, "reason": str}'
        ),
        messages=[{"role": "user", "content":
            f"Profile:\n{json.dumps(ctx, default=str)}\n\nField type: {kind}\nQuestion: {question}{opts}"}],
    )
    txt = "".join(b.text for b in msg.content if b.type == "text")
    try:
        return json.loads(txt.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception:
        return {"answer": None, "confidence": 0.0, "reason": f"unparseable: {txt[:80]}"}


def _parse_json(txt, default):
    try:
        return json.loads(txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except Exception:
        return default


def candidate_brief(profile: dict) -> str:
    """One short paragraph describing who the candidate is, from profile + résumé PDF.
    Cached per process. Returns a profile-only brief when no API key / no résumé file."""
    global _brief
    if _brief is not None:
        return _brief
    ctx = {"search": profile.get("search", {}), "work": profile.get("work", {}),
           "candidate": {k: v for k, v in profile.get("candidate", {}).items() if "path" not in k}}
    if not available():
        _brief = json.dumps(ctx, default=str); return _brief
    resume_path = (profile.get("candidate", {}) or {}).get("resume_path")
    content = []
    try:
        # résumé-aware matching reads a PDF; any other format (or none) falls back to profile text
        if resume_path and str(resume_path).lower().endswith(".pdf") and Path(resume_path).exists():
            data = base64.standard_b64encode(Path(resume_path).read_bytes()).decode()
            content.append({"type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": data}})
    except Exception:
        pass
    content.append({"type": "text", "text":
        f"Profile preferences:\n{json.dumps(ctx, default=str)}\n\n"
        "Write a 3-4 sentence brief of this candidate for matching job titles: their target "
        "roles/seniority, core skills/domain, and any hard constraints (location, level). "
        "Plain text, no preamble."})
    try:
        msg = _cl().messages.create(model=MODEL, max_tokens=400,
                                    messages=[{"role": "user", "content": content}])
        _brief = "".join(b.text for b in msg.content if b.type == "text").strip() or json.dumps(ctx, default=str)
    except Exception:
        _brief = json.dumps(ctx, default=str)
    return _brief


def rank_roles(items: list, brief: str, near: str = "", relocate: bool = False, batch: int = 40) -> list:
    """items = [(title, location)]. Return [(keep: bool, reason: str)] aligned to items.
    Keeps roles that fit the candidate brief AND (when `near` is set) the location preference.
    No API key → returns all True (caller should use the keyword filter instead)."""
    if not available() or not items:
        return [(True, "") for _ in items]
    if near:
        loc_rule = (f"LOCATION: keep a role only if its location is within commuting range of "
                    f"'{near}' — keep Remote/anywhere roles too. "
                    + ("Out-of-area roles that are a strong fit may be kept as relocation options "
                       "(note 'relocate' in the reason)." if relocate
                       else "Drop roles whose location is clearly outside that area (e.g. other metros)."))
    else:
        loc_rule = "Location is not a filter."
    out = []
    for start in range(0, len(items), batch):
        chunk = items[start:start + batch]
        listing = "\n".join(f"{i}. {t}  [location: {loc or 'unspecified'}]" for i, (t, loc) in enumerate(chunk))
        msg = _cl().messages.create(
            model=MODEL, max_tokens=1500,
            system=("You match job postings to a candidate brief. Keep a posting only if it is a "
                    "plausible fit for the candidate's target roles and seniority; drop unrelated "
                    "functions and clearly wrong levels. Be inclusive on borderline role fit. "
                    f"{loc_rule} "
                    'Respond ONLY with JSON: {"keep": [indices], "reasons": {"index": "short why"}}'),
            messages=[{"role": "user", "content":
                       f"Candidate brief:\n{brief}\n\nPostings:\n{listing}"}])
        txt = "".join(b.text for b in msg.content if b.type == "text")
        res = _parse_json(txt, None)
        if res is None:   # fail closed (keep none) + warn, rather than silently keeping everything unfiltered
            print(f"  warning: LLM match response unparseable for a batch of {len(chunk)} role(s) — "
                  f"keeping none from this batch; re-run to retry")
            res = {"keep": [], "reasons": {}}
        keep = set(res.get("keep", []))
        reasons = res.get("reasons", {}) or {}
        for i, _ in enumerate(chunk):
            out.append((i in keep, str(reasons.get(str(i), ""))))
    return out
