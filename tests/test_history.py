import json, os, tempfile, unittest
from fleet import history

def ts(minute, day=13, hour=10):
    return f"2026-09-{day:02d}T{hour:02d}:{minute:02d}:00Z"

class Scan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self, *records):
        d = os.path.join(self.tmp.name, "-home-u-work"); os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "aaaaaaaa-0000-4000-8000-000000000001.jsonl")
        with open(p, "w") as f:
            for r in records:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
        return history.scan(p)

    @staticmethod
    def user(text, t):
        return {"type": "user", "timestamp": t, "message": {"content": text}}

    def test_no_timestamps_is_none(self):
        self.assertIsNone(self.scan({"type": "agent-name", "agentName": "a"}))

    def test_span_bins_cwd_versions(self):
        r = self.scan({"type": "user", "timestamp": ts(0), "cwd": "/home/u/work", "version": "2.1.1",
                       "message": {"content": "hi"}},
                      {"type": "assistant", "timestamp": ts(40), "version": "2.1.2", "message": {"content": []}})
        self.assertEqual((r["cwd"], r["versions"]), ("/home/u/work", ["2.1.1", "2.1.2"]))
        self.assertEqual(len(r["bins"]), 2)                     # 10:00 and 10:40 are different bins
        self.assertEqual(r["last"] - r["first"], 2400)
        self.assertEqual(sorted(r["version_seen"]), ["2.1.1", "2.1.2"])

    def test_clear_only_at_the_start(self):
        clear = "<command-name>/clear</command-name>"
        self.assertTrue(self.scan(self.user("x", ts(0)), self.user(clear, ts(1)))["clear"])
        late = [self.user(f"m{i}", ts(i)) for i in range(3)] + [self.user(clear, ts(5))]
        self.assertFalse(self.scan(*late)["clear"])

    def test_compactions_merge_within_ten_minutes(self):
        boundary = lambda m: {"type": "system", "subtype": "compact_boundary", "timestamp": ts(m)}
        summary = lambda m: {"type": "user", "timestamp": ts(m), "isCompactSummary": True, "message": {"content": "s"}}
        self.assertEqual(len(self.scan(boundary(0), summary(1))["compact"]), 1)
        self.assertEqual(len(self.scan(boundary(0), boundary(30))["compact"]), 2)
        self.assertEqual(self.scan(self.user("no compaction", ts(0)))["compact"], [])

    def test_rename_takes_the_preceding_timestamp(self):
        r = self.scan({"type": "agent-name", "agentName": "old"}, self.user("a", ts(5)),
                      {"type": "agent-name", "agentName": "old"}, self.user("b", ts(9)),
                      {"type": "agent-name", "agentName": "new"})
        self.assertEqual(len(r["renames"]), 1)
        t, a, b = r["renames"][0]
        self.assertEqual((a, b), ("old", "new"))
        self.assertEqual(t, r["last"])
        self.assertEqual(r["agent_names"][-1], "new")

    def test_self_report_inside_a_tool_result_is_a_name(self):
        r = self.scan({"type": "user", "timestamp": ts(0), "message": {"content": [
            {"type": "tool_result", "content": "This session is alpha [abcdef] -- the name"}]}})
        self.assertEqual([n for _, n in r["names"]], ["alpha"])

    def test_messages_sent_and_received_once_per_delivery(self):
        env = '<cross-session-message from-name="b">\nhello\n</cross-session-message>'
        r = self.scan({"type": "queue-operation", "timestamp": ts(0), "content": env},
                      self.user(env, ts(0)), self.user(env + "\n\nharness note", ts(1)),
                      {"type": "assistant", "timestamp": ts(2), "message": {"content": [
                          {"type": "tool_use", "name": "SendMessage", "input": {"to": "b", "message": "x"}},
                          {"type": "tool_use", "name": "Bash", "input": {}}]}})
        self.assertEqual((r["sent"], r["received"]), (1, 1))

if __name__ == "__main__":
    unittest.main()
