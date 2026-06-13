"""liveness(): conservative closed-detection — must not false-flag live roles as closed."""
import unittest
from run import liveness


class FakeResp:
    def __init__(self, status_code, url, text=""):
        self.status_code, self.url, self.text = status_code, url, text


class FakeClient:
    def __init__(self, resp): self._resp = resp
    def get(self, url, **kw): return self._resp


def check(orig_url, status, final_url, text=""):
    state, _ = liveness(FakeClient(FakeResp(status, final_url, text)), orig_url)
    return state


class TestLiveness(unittest.TestCase):
    def test_404_is_closed(self):
        self.assertEqual(check("https://x/jobs/100001", 404, "https://x/jobs/100001"), "closed")

    def test_live_page(self):
        self.assertEqual(check("https://x/jobs/100001", 200, "https://x/jobs/100001",
                               "<h1>Senior Designer</h1> apply now"), "live")

    def test_strong_closed_phrase(self):
        self.assertEqual(check("https://x/jobs/100001", 200, "https://x/jobs/100001",
                               "This role is no longer accepting applications."), "closed")

    def test_redirect_to_listing_is_closed(self):
        # job-id URL redirected to a board listing that dropped the id
        self.assertEqual(check("https://b.greenhouse.io/acme/jobs/100001", 200,
                               "https://b.greenhouse.io/acme/jobs"), "closed")

    def test_id_rewrite_is_not_closed(self):
        # id absent from final URL but it's NOT a listing path -> still live (the conservative fix)
        self.assertEqual(check("https://x/jobs/100001", 200,
                               "https://x/job/senior-designer?gh_src=abc",
                               "Senior Designer — apply"), "live")

    def test_benign_text_not_closed(self):
        # loose words like "position" must NOT trigger closed without a strong phrase
        self.assertEqual(check("https://x/jobs/100001", 200, "https://x/jobs/100001",
                               "We value every position and posting on our team."), "live")


if __name__ == "__main__":
    unittest.main()
