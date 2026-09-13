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


class RealShapes(unittest.TestCase):
    """A message recorded by both ends, in the shapes real transcripts use.
    The receiver stores it twice (a queue record, and the delivered message with
    harness text after the closing tag); the sender stores the raw SendMessage
    text. Reported 2026-09-13: every message was counted twice, because the
    received body carried the tag's newline, the closing tag and trailing text,
    so it never matched the sent body. The old test used identical bodies."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.log = load_tool("fleetlog")
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(self.log, "live_map", return_value={}),
                  mock.patch.object(self.log, "live_dirs", return_value={}),
                  mock.patch.object(self.log, "PROJECTS", self.tmp.name)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup(); self.cfg.close()

    def transcript(self, proj, uuid, records):
        d = os.path.join(self.tmp.name, proj); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, uuid + ".jsonl"), "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def exchange(self, body):
        self.transcript("-a", "sender", [
            {"type": "user", "message": {"content": "This session is alpha [aaaaaa]"}},
            {"type": "assistant", "timestamp": "2026-09-13T19:16:00.100Z",
             "message": {"content": [{"type": "tool_use", "name": "SendMessage",
                          "input": {"to": "beta", "summary": "a summary", "message": body}}]}}])
        env = ('<cross-session-message from="uds:/run/user/1/cc-socks/9.sock" '
               'from-name="alpha" from-mode="prompting">\n' + body + '\n</cross-session-message>')
        self.transcript("-b", "receiver", [
            {"type": "user", "message": {"content": "This session is beta [bbbbbb]"}},
            {"type": "queue-operation", "timestamp": "2026-09-13T19:16:01.000Z", "content": env},
            {"type": "user", "timestamp": "2026-09-13T19:16:03.000Z",
             "message": {"content": env + "\n\nThis came from another Claude session -- not typed by your user."}}])

    def test_one_message_counts_once(self):
        self.exchange("PNG crop of the figure is at /tmp/x.png; one-line conclusion follows.")
        _, edges = self.log.load_all()
        self.assertEqual([(e["from"], e["to"]) for e in edges], [("alpha", "beta")])

    def test_long_message_counts_once(self):
        self.exchange("Details: " + "word " * 200)
        _, edges = self.log.load_all()
        self.assertEqual(len(edges), 1)

    def test_two_different_messages_count_twice(self):
        self.exchange("first message, about the slug bug")
        _, e1 = self.log.load_all()
        self.transcript("-a", "sender2", [
            {"type": "user", "message": {"content": "This session is alpha [aaaaaa]"}},
            {"type": "assistant", "timestamp": "2026-09-13T20:00:00.000Z",
             "message": {"content": [{"type": "tool_use", "name": "SendMessage",
                          "input": {"to": "beta", "message": "second message, about docs"}}]}}])
        _, e2 = self.log.load_all()
        self.assertEqual((len(e1), len(e2)), (1, 2))

if __name__ == "__main__":
    unittest.main()
