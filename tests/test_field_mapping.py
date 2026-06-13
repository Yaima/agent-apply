"""map_field: the safety-critical invariant — sensitive data is NEVER guessed, and a
missing required résumé routes to a human instead of submitting without one."""
import os, tempfile, unittest
from agent.forms.common import Field, map_field, get


def mk(kind, label, required=True, options=None):
    return Field(handle=None, kind=kind, label=label, required=required, options=options or [])


class TestGet(unittest.TestCase):
    def test_dotted_path(self):
        p = {"candidate": {"email": "a@b.com"}}
        self.assertEqual(get(p, "candidate.email"), "a@b.com")
        self.assertIsNone(get(p, "candidate.missing"))
        self.assertIsNone(get(p, "nope.deep.path"))


class TestMapField(unittest.TestCase):
    def setUp(self):
        self.resume = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.resume.write(b"%PDF-1.4 fake"); self.resume.close()
        self.profile = {
            "candidate": {"first_name": "Sam", "email": "sam@example.com",
                          "resume_path": self.resume.name},
            "work": {"work_authorization": True, "salary_expectation": None},
            "eeoc": {"gender": "Male", "disability_status": None},
            "answers": {"custom": [{"match": r"why .*join", "answer": "Because mission"}]},
        }

    def tearDown(self):
        os.unlink(self.resume.name)

    def test_profile_field(self):
        self.assertEqual(map_field(mk("text", "First Name"), self.profile), ("Sam", "profile"))

    def test_sensitive_present(self):
        self.assertEqual(map_field(mk("text", "Gender"), self.profile), ("Male", "sensitive"))

    def test_sensitive_bool_becomes_yes(self):
        v, s = map_field(mk("text", "Are you authorized to work?"), self.profile)
        self.assertEqual((v, s), ("Yes", "sensitive"))

    def test_sensitive_missing_no_option_is_never_guessed(self):
        # salary has no profile value and no decline option -> routes to human, not guessed
        self.assertEqual(map_field(mk("text", "Salary expectation"), self.profile),
                         (None, "sensitive-missing"))

    def test_sensitive_missing_picks_decline_option(self):
        f = mk("select", "Disability status", options=[("Yes", 0), ("No", 1),
                                                        ("I don't wish to answer", 2)])
        v, s = map_field(f, self.profile)
        self.assertEqual(s, "decline")
        self.assertIn("wish", v.lower())

    def test_resume_file_present(self):
        v, s = map_field(mk("file", "Resume/CV"), self.profile)
        self.assertEqual((v, s), (self.resume.name, "profile"))

    def test_resume_file_missing_routes_to_human(self):
        self.profile["candidate"]["resume_path"] = "resume/does_not_exist.pdf"
        self.assertEqual(map_field(mk("file", "Resume"), self.profile), (None, "file-missing"))

    def test_custom_answer(self):
        v, s = map_field(mk("textarea", "Why do you want to join us?"), self.profile)
        self.assertEqual((v, s), ("Because mission", "profile"))


if __name__ == "__main__":
    unittest.main()
