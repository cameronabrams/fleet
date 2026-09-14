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
        self.assertEqual((ident, how), ("alpha", "own ListAgents self-report"))
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


class Identity(unittest.TestCase):
    """Whose transcript is this? OBSERVED 2026-09-14: the original coordinator
    transcript -- agent-name 'coord' throughout -- was reported as another session,
    because identity came from the FIRST self-report (an old name) and was then
    mapped through the fleet-wide old-name table, where that name had later
    belonged to someone else. Names are reused; a transcript's own last name
    record is what identifies it."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmp = tempfile.TemporaryDirectory()
        json.dump({"sessions": [{"label": "coord", "cwd": "/home/u"},
                                {"label": "notebook", "cwd": "/home/u/site"},
                                {"label": "study", "cwd": "/home/u/runs"}]},
                  open(os.path.join(self.cfg.state, "manifest.json"), "w"))
        self.log = load_tool("fleetlog")
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
        path = os.path.join(d, uuid + ".jsonl")
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path

    @staticmethod
    def said(name):
        return {"type": "user", "message": {"content": f"This session is {name} [abcdef]"}}

    def test_last_agent_name_wins_over_first_self_report(self):
        # the old name 'x-7e' later belonged to the site session's transcript
        site = self.transcript("-home-u-site", "site", [self.said("x-7e"), self.said("notebook")])
        coord = self.transcript("-home-u", "coord", [
            {"type": "agent-name", "agentName": "coord"}, self.said("x-7e"),
            {"type": "agent-name", "agentName": "coord"}])
        # the site transcript is newer, so the old-name table maps x-7e -> notebook
        os.utime(coord, (1000, 1000)); os.utime(site, (2000, 2000))
        self.assertEqual(self.log.name_map().get("x-7e"), "notebook")
        ident, how, _ = self.log.parse_transcript(coord)
        self.assertEqual(ident, "coord", how)

    def test_renamed_transcript_is_its_latest_name(self):
        repo = self.transcript("-home-u-repo", "repo", [
            {"type": "agent-name", "agentName": "study"}, self.said("study"),
            {"type": "agent-name", "agentName": "repo-now"}])
        self.assertEqual(self.log.parse_transcript(repo)[0], "repo-now")

    def test_retired_name_goes_to_its_own_directory_owner(self):
        old = self.transcript("-home-u-runs", "old", [self.said("runs-41")])
        ident, how, _ = self.log.parse_transcript(old)
        self.assertEqual(ident, "study")
        self.assertIn("directory", how)

    def test_retired_name_with_no_owner_stays_as_written(self):
        old = self.transcript("-home-u-gone", "old", [{"type": "agent-name", "agentName": "gone-9"}])
        self.assertEqual(self.log.parse_transcript(old)[0], "gone-9")

if __name__ == "__main__":
    unittest.main()
