"""ATS detection + rewrite: the routing that decides automate vs. human."""
import unittest
from agent.ats import classify, rewrite, AUTOMATABLE, RECAPTCHA_V3


class TestClassify(unittest.TestCase):
    def test_known_domains(self):
        self.assertEqual(classify("https://job-boards.greenhouse.io/acme/jobs/123"), "greenhouse")
        self.assertEqual(classify("https://jobs.lever.co/acme/abc"), "lever")
        self.assertEqual(classify("https://jobs.ashbyhq.com/acme/role"), "ashby")
        self.assertEqual(classify("https://jobs.apple.com/en-us/details/200/x"), "apple_careers")
        self.assertEqual(classify("https://www.linkedin.com/jobs/view/1"), "linkedin")
        self.assertEqual(classify("https://careers.google.com/jobs/results/1"), "google_careers")

    def test_markers_from_html_or_final_url(self):
        # MARKERS inspect final_url/html, not the bare url
        self.assertEqual(classify("https://x.example/apply", html="<a>myworkdayjobs.com</a>"), "workday")
        self.assertEqual(classify("https://x.example", final_url="https://y.greenhouse.io/z"), "greenhouse")

    def test_unknown_is_custom(self):
        self.assertEqual(classify("https://careers.salesforce.com/en/jobs/jr1"), "custom")

    def test_automatable_and_v3_sets(self):
        # only these three auto-fill; apple/google/workday/custom go to assist/Exceptions
        self.assertEqual(AUTOMATABLE, {"greenhouse", "lever", "ashby"})
        for a in ("apple_careers", "google_careers", "workday", "custom", "linkedin"):
            self.assertNotIn(a, AUTOMATABLE)
        # ashby is automatable BUT v3 — must never be auto-submitted
        self.assertIn("ashby", RECAPTCHA_V3)
        self.assertIn("ashby", AUTOMATABLE)


class TestRewrite(unittest.TestCase):
    def test_custom_domain_maps_to_greenhouse_embed(self):
        out = rewrite("https://careers.roblox.com/jobs/4567890")
        self.assertIn("greenhouse.io", out)
        self.assertIn("4567890", out)

    def test_passthrough_when_no_rule(self):
        url = "https://job-boards.greenhouse.io/figma/jobs/1"
        self.assertEqual(rewrite(url), url)


if __name__ == "__main__":
    unittest.main()
