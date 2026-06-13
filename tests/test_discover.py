"""Dedup id extraction — uses the LAST long number so board/segment ids don't collapse roles."""
import unittest
from discover import jobid, _wd_sites


class TestJobId(unittest.TestCase):
    def test_greenhouse_job_id(self):
        self.assertEqual(jobid("https://job-boards.greenhouse.io/acme/jobs/4567890"), "4567890")

    def test_uses_last_number_not_board_segment(self):
        # a board/segment number must not become the key (that would collapse every role on it)
        self.assertEqual(jobid("https://x/boards/123456/jobs/789012"), "789012")

    def test_no_long_number(self):
        self.assertIsNone(jobid("https://jobs.lever.co/acme/some-uuid-slug"))

    def test_apple_style(self):
        self.assertEqual(jobid("https://jobs.apple.com/en-us/details/200667495-3543/x"), "200667495")


class TestWorkdaySiteTemplates(unittest.TestCase):
    def test_includes_common_patterns(self):
        sites = _wd_sites("nvidia")
        self.assertIn("NVIDIAExternalCareerSite", sites)
        self.assertIn("Nvidia_Careers", sites)
        self.assertIn("External", sites)


if __name__ == "__main__":
    unittest.main()
