import json, os, tempfile, unittest
from tests.support import BASE_TOML, FakeConfig, load_tool

def assistant(text, ts="2026-09-13T10:00:00Z"):
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"content": [{"type": "text", "text": text}]}}) + "\n"

def user(text):
    return json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}}) + "\n"

class Waiting(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML + '\n[human]\nname = "Alex"\naliases = ["the PI"]\n')
        self.w = load_tool("fleetwaiting")
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup(); self.cfg.close()

    def scan(self, *lines):
        p = os.path.join(self.tmp.name, "t.jsonl")
        open(p, "w").writelines(lines)
        return self.w.scan(p)

    def test_blocked_on_named_human(self):
        line, ts, resolved = self.scan(assistant("Done with the tests. I am waiting on Alex for the push decision."))
        self.assertIn("waiting on Alex", line)
        self.assertFalse(resolved)

    def test_alias_and_generic_words(self):
        self.assertIsNotNone(self.scan(assistant("This one is the PI's call, not mine to make."))[0])
        self.assertIsNotNone(self.scan(assistant("That is blocked on the human until tomorrow."))[0])

    def test_resolution_after(self):
        _, _, resolved = self.scan(assistant("Still waiting on Alex about the release."),
                                   user("Alex approved the release"))
        self.assertTrue(resolved)

    def test_messages_sent_to_the_session_are_not_its_own_words(self):
        self.assertEqual(self.scan(user("coord: I am waiting on Alex for the budget answer."))[0], None)

    def test_name_is_a_word_not_a_substring(self):
        self.assertIsNone(self.scan(assistant("We are waiting on Alexander's cluster to drain."))[0])

    def test_without_configured_name_only_generic_words(self):
        blocked, _ = self.w.patterns({})
        self.assertTrue(blocked.search("blocked on the user for this"))
        self.assertFalse(blocked.search("waiting on Alex for this"))

if __name__ == "__main__":
    unittest.main()
