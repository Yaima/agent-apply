"""LLM helpers degrade gracefully with no API key, and JSON parsing fails closed."""
import os, unittest
from unittest import mock
from agent import llm


class TestParseJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(llm._parse_json('{"a": 1}', None), {"a": 1})

    def test_fenced(self):
        self.assertEqual(llm._parse_json('```json\n{"a": 1}\n```', None), {"a": 1})

    def test_unparseable_returns_default(self):
        self.assertIsNone(llm._parse_json("not json at all", None))


class TestNoKeyFallback(unittest.TestCase):
    def setUp(self):
        llm._brief = None  # clear module cache
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def tearDown(self):
        self.env.stop()
        llm._brief = None

    def test_available_false(self):
        self.assertFalse(llm.available())

    def test_rank_roles_keeps_all_without_key(self):
        # without a key, ranking is a no-op (caller uses the keyword filter instead)
        items = [("UX Designer", "SF"), ("Truck Driver", "TX")]
        self.assertEqual(llm.rank_roles(items, "brief"), [(True, ""), (True, "")])

    def test_candidate_brief_falls_back_to_profile_text(self):
        brief = llm.candidate_brief({"search": {"roles": ["designer"]}, "candidate": {}})
        self.assertIsInstance(brief, str)
        self.assertIn("designer", brief)


if __name__ == "__main__":
    unittest.main()
