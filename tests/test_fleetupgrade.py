import json, os, tempfile, time, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
CWD = "/home/u/work"
SLUG = "-home-u-work"

class Upgrade(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmp = tempfile.TemporaryDirectory()
        self.up = load_tool("fleetupgrade")
        self.projects = os.path.join(self.tmp.name, "projects")
        self.scratch = os.path.join(self.tmp.name, "scratch")
        os.makedirs(os.path.join(self.projects, SLUG))
        self.patches = [mock.patch.object(self.up, "PROJECTS", self.projects),
                        mock.patch.object(self.up, "SCRATCH", self.scratch)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup(); self.cfg.close()

    def transcript(self, uuid, records, mtime=None):
        path = os.path.join(self.projects, SLUG, uuid + ".jsonl")
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        os.makedirs(os.path.join(self.scratch, SLUG, uuid), exist_ok=True)

    def test_uuid_from_cmdline(self):
        self.assertEqual(self.up.uuid_from_cmdline(f"claude --name x --resume {U1}"), U1)
        self.assertIsNone(self.up.uuid_from_cmdline("claude --name x"))
        self.assertIsNone(self.up.uuid_from_cmdline(None))

    def test_name_is_last_agent_name_record(self):
        # /rename writes mid-file; the header still carries the old name
        self.transcript(U1, [{"type": "agent-name", "agentName": "old"},
                             {"type": "user"},
                             {"type": "agent-name", "agentName": "new"}])
        self.assertEqual(self.up.name_from_transcript(CWD, U1), "new")
        self.assertIsNone(self.up.name_from_transcript(CWD, None))

    def test_colour_is_last_record(self):
        self.transcript(U1, [{"type": "agent-color", "agentColor": "red"},
                             {"type": "agent-color", "agentColor": "blue"}])
        self.assertEqual(self.up.color_from_transcript(CWD, U1), "blue")

    def test_live_uuids_skip_transcripts_older_than_the_process(self):
        # an exited session leaves its scratchpad behind: not a candidate
        now = time.time()
        self.transcript(U1, [], mtime=now - 7200)
        self.transcript(U2, [], mtime=now - 10)
        self.assertEqual(self.up.live_uuids(CWD, 5, since=now - 3600), [U2])
        self.assertEqual(self.up.live_uuids(CWD, 5), [U2, U1])

    def test_running_claude_preferred_over_stopped(self):
        # a Ctrl-Z'd claude and a live one in the same pane: take the live one
        cmd = {"100": "claude --name a", "200": "claude --name a", "300": "bash"}
        state = {"100": "S", "200": "T", "300": "S"}
        real_open = open
        def fake_open(path, *a, **kw):
            pid = path.split("/")[2] if path.startswith("/proc/") else None
            if pid in cmd and path.endswith("/cmdline"):
                import io
                return io.BytesIO(cmd[pid].replace(" ", "\0").encode())
            return real_open(path, *a, **kw)
        with mock.patch.object(self.up, "sh", return_value="100\n200\n300\n"), \
             mock.patch.object(self.up, "proc_state", side_effect=lambda p: state[p]), \
             mock.patch("builtins.open", side_effect=fake_open):
            self.assertEqual(self.up.claude_pid("1")[0], "100")
            state["100"] = "T"
            self.assertEqual(self.up.claude_pid("1")[0], "200")   # all stopped: newest

if __name__ == "__main__":
    unittest.main()
