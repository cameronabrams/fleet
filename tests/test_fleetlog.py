import json, os, tempfile, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

class Log(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.log = load_tool("fleetlog")
        self.tmp = tempfile.TemporaryDirectory()
        # no manifest in the fake state dir, so names pass through un-mapped
        self.p = [mock.patch.object(self.log, "live_map", return_value={}),
                  mock.patch.object(self.log, "live_dirs", return_value={})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup(); self.cfg.close()

    def test_parse_in_and_out(self):
        path = os.path.join(self.tmp.name, "t.jsonl")
        envelope = ('<cross-session-message from="uds:/run/x/1.sock" from-name="beta">'
                    'Please look at the slug bug\nmore</cross-session-message>')
        with open(path, "w") as f:
            f.write(json.dumps({"type": "user", "timestamp": "2026-09-13T10:00:00Z",
                                "message": {"content": "This session is alpha [abc123]"}}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": "2026-09-13T10:01:00Z",
                                "message": {"content": envelope}}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": "2026-09-13T10:01:01Z",
                                "message": {"content": envelope}}) + "\n")   # queued + delivered
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-09-13T10:02:00Z",
                                "message": {"content": [{"type": "tool_use", "name": "SendMessage",
                                            "input": {"to": "beta", "summary": "fixed",
                                                      "message": "done"}}]}}) + "\n")
        ident, how, events = self.log.parse_transcript(path)
        self.assertEqual((ident, how), ("alpha", "ListAgents self-report"))
        self.assertEqual([(e["dir"], e["peer"]) for e in events], [("in", "beta"), ("out", "beta")])
        self.assertEqual(events[0]["subject"], "Please look at the slug bug")

    def test_dedupe_keeps_one_copy_per_message(self):
        e = {"from": "a", "to": "b", "ts": "2026-09-13T10:00:00.000Z", "body": "hello"}
        other_side = dict(e, ts="2026-09-13T10:00:03.000Z")    # recipient's stamp
        different = dict(e, body="goodbye")
        self.assertEqual(len(self.log.dedupe([e, dict(e), other_side, different])), 2)

    def test_canon_strips_ref(self):
        self.assertEqual(self.log.canon("beta [abc123]"), "beta")
        self.assertIsNone(self.log.canon(""))

if __name__ == "__main__":
    unittest.main()
