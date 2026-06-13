import re
from urllib.parse import urlparse

MARKERS = [
    ("greenhouse", re.compile(r"greenhouse\.io|grnhse", re.I)),
    ("ashby", re.compile(r"ashbyhq\.com|ashby_embed", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co|lever-analytics", re.I)),
    ("workday", re.compile(r"myworkdayjobs\.com", re.I)),
    ("smartrecruiters", re.compile(r"smartrecruiters\.com", re.I)),
    ("icims", re.compile(r"icims\.com", re.I)),
]
DOMAIN = {
    "job-boards.greenhouse.io": "greenhouse", "boards.greenhouse.io": "greenhouse",
    "jobs.ashbyhq.com": "ashby", "jobs.lever.co": "lever",
    "www.linkedin.com": "linkedin", "careers.google.com": "google_careers",
    "www.google.com": "google_careers", "jobs.apple.com": "apple_careers",
}
AUTOMATABLE = {"greenhouse", "lever", "ashby"}
RECAPTCHA_V3 = {"ashby"}  # invisible reCAPTCHA v3: fill for reference, never auto-submit; apply by hand

REWRITES = [
    (re.compile(r"https?://careers\.roblox\.com/jobs/(\d+)"), r"https://boards.greenhouse.io/embed/job_app?for=roblox&token=\1"),
    (re.compile(r"https?://www\.pinterestcareers\.com/jobs/(\d+)"), r"https://boards.greenhouse.io/embed/job_app?for=pinterest&token=\1"),
]
def rewrite(url: str) -> str:
    for rx, rep in REWRITES:
        m = rx.match(url)
        if m: return rx.sub(rep, url, count=1)
    return url

def classify(url: str, html: str = "", final_url: str = "") -> str:
    dom = urlparse(url).netloc
    if dom in DOMAIN:
        return DOMAIN[dom]
    for name, rx in MARKERS:
        if rx.search(final_url or "") or rx.search(html or ""):
            return name
    return "custom"
