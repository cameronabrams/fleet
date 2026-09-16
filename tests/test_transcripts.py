import json, os, tempfile, time, unittest
from unittest import mock
from fleet import transcripts as tr

def rec(**kw):
    return json.dumps(kw) + "\n"

class Transcripts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = os.path.join(self.tmp.name, "-home-u-work")
        os.makedirs(self.proj)
        self.p = mock.patch.object(tr, "PROJECTS", self.tmp.name)
        self.p.start()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def write(self, uuid, lines, mtime=None):
        path = os.path.join(self.proj, uuid + ".jsonl")
        with open(path, "w") as f:
            f.writelines(lines)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_agent_color_takes_last(self):
        self.write("u1", [rec(type="agent-color", agentColor="red"),
                          rec(type="user"),
                          rec(type="agent-color", agentColor="blue")])
        self.assertEqual(tr.agent_color("u1"), "blue")
        self.assertIsNone(tr.agent_color("absent"))
        self.assertIsNone(tr.agent_color(None))

    def test_first_timestamp(self):
        p = self.write("u1", [rec(type="agent-name"),
                              rec(type="user", timestamp="2026-09-13T12:00:00Z")])
        self.assertEqual(tr.first_timestamp(p), 1789300800.0)
        self.assertIsNone(tr.first_timestamp(os.path.join(self.proj, "none.jsonl")))

    def cleared(self, started, label="alpha"):
        with mock.patch.object(tr, "process_start", return_value=started):
            return tr.cleared_successor("argv", label, 1)

    def iso(self, t):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))

    def test_cleared_successor_found(self):
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200), agentName="alpha")], now - 3600)
        self.write("succ", [rec(timestamp=self.iso(now - 600), agentName="alpha")], now - 60)
        self.assertEqual(self.cleared(now - 5000), ("succ", 1))

    def test_resumed_file_predating_launch_is_not_a_successor(self):
        # a newer file whose first record predates the process: a resume, not a /clear
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200), agentName="alpha")], now - 3600)
        self.write("other", [rec(timestamp=self.iso(now - 9000), agentName="alpha")], now - 60)
        self.assertEqual(self.cleared(now - 5000), (None, 0))

    def test_other_sessions_file_is_not_a_successor(self):
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200), agentName="alpha")], now - 3600)
        self.write("beta", [rec(timestamp=self.iso(now - 600), agentName="beta")], now - 60)
        self.assertEqual(self.cleared(now - 5000), (None, 0))

    def test_older_file_is_not_a_successor(self):
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200), agentName="alpha")], now - 60)
        self.write("stale", [rec(timestamp=self.iso(now - 600), agentName="alpha")], now - 3600)
        self.assertEqual(self.cleared(now - 5000), (None, 0))

    def test_several_candidates_newest_and_counted(self):
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200), agentName="alpha")], now - 3600)
        self.write("s1", [rec(timestamp=self.iso(now - 900), agentName="alpha")], now - 300)
        self.write("s2", [rec(timestamp=self.iso(now - 600), agentName="alpha")], now - 60)
        self.assertEqual(self.cleared(now - 5000), ("s2", 2))

    def test_name_match_ignores_case_and_dashes(self):
        now = time.time()
        self.write("argv", [rec(timestamp=self.iso(now - 7200))], now - 3600)
        self.write("succ", [rec(timestamp=self.iso(now - 600), agentName="Fleet Repo")], now - 60)
        self.assertEqual(self.cleared(now - 5000, label="fleet-repo"), ("succ", 1))

    def test_uuid_from_descendants_reads_own_process_tree(self):
        import subprocess, sys
        uuid = "aaaaaaaa-0000-4000-8000-000000000001"
        fake = f"/tmp/claude-{os.getuid()}/-proj/{uuid}/scratchpad/x"
        plain = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertIsNone(tr.uuid_from_descendants(plain.pid))
        finally:
            plain.kill(); plain.wait()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", fake])
        try:
            self.assertEqual(tr.uuid_from_descendants(os.getpid()), uuid)
        finally:
            child.kill(); child.wait()

    def test_session_name_follows_rename_not_argv(self):
        u = "bbbbbbbb-0000-4000-8000-000000000002"
        self.write(u, [rec(type="agent-name", agentName="old"), rec(type="user", timestamp="2026-09-13T10:00:00Z"),
                       rec(type="agent-name", agentName="old-repo")])
        argv = ["claude", "--name", "old", "--resume", u]
        with mock.patch.object(tr, "process_start", return_value=None):
            name, uuid, how = tr.session_name(1, "/home/u/work", argv)
        self.assertEqual((name, uuid), ("old-repo", u))
        self.assertIn("renamed since launch", how)
        self.assertTrue(how.startswith("verified"), how)     # fleetretire requires it

    def test_session_name_unrenamed_and_unresolved(self):
        u = "bbbbbbbb-0000-4000-8000-000000000003"
        self.write(u, [rec(type="agent-name", agentName="alpha"), rec(type="user", timestamp="2026-09-13T10:00:00Z")])
        with mock.patch.object(tr, "process_start", return_value=None):
            self.assertEqual(tr.session_name(1, "/w", ["claude", "--name", "alpha", "--resume", u])[0], "alpha")
        with mock.patch.object(tr, "resume_handle", return_value=(None, "no transcript found")):
            self.assertEqual(tr.session_name(1, "/w", ["claude", "--name", "beta"])[0], "beta")

    def asst(self, n_in, n_read, n_create, sidechain=False):
        return rec(type="assistant", isSidechain=sidechain,
                   message={"usage": {"input_tokens": n_in, "cache_read_input_tokens": n_read,
                                      "cache_creation_input_tokens": n_create, "output_tokens": 9}})

    def boundary(self, pre, post, ts="2026-09-15T12:00:00Z"):
        return rec(type="system", subtype="compact_boundary", timestamp=ts, uuid="b",
                   compactMetadata={"trigger": "manual", "preTokens": pre, "postTokens": post})

    def turn(self):
        return rec(type="system", subtype="turn_duration")

    def test_context_is_last_main_thread_turn(self):
        self.write("u1", [rec(type="user", timestamp="2026-09-13T12:00:00Z"),
                          self.asst(2, 1000, 50), self.turn(),
                          self.asst(3, 2000, 10), self.turn(),
                          self.asst(5, 90000, 0, sidechain=True),      # a subagent's turn
                          self.asst(0, 0, 0)])                          # a synthetic message
        st = tr.context_stats("u1")
        self.assertEqual(st["tokens"], 2013)
        self.assertEqual((st["compactions"], st["turns"]), (0, 2))
        self.assertEqual(st["since"], 1789300800.0)                   # no compaction: first record
        self.assertIsNone(st["last_compact"])

    def test_compaction_resets_size_turns_and_since(self):
        self.write("u1", [rec(type="user", timestamp="2026-09-13T12:00:00Z"),
                          self.asst(2, 300000, 0), self.turn(), self.turn(),
                          self.boundary(300002, 9000)])
        st = tr.context_stats("u1")
        self.assertEqual(st["tokens"], 9000)                           # postTokens until the next turn
        self.assertEqual((st["compactions"], st["turns"]), (1, 0))
        self.assertEqual(st["since"], 1789473600.0)
        self.assertEqual(st["last_compact"]["pre"], 300002)
        self.write("u1", [self.boundary(300002, 9000), self.asst(1, 12000, 500), self.turn()])
        self.assertEqual(tr.context_stats("u1")["tokens"], 12501)
        self.assertEqual(tr.context_stats("u1")["turns"], 1)

    def test_text_mentioning_a_boundary_is_not_one(self):
        self.write("u1", [rec(type="user", message={"content": 'grep "compact_boundary" x'}),
                          rec(type="attachment", name="compact_boundary"),     # the bare word, unescaped
                          rec(type="assistant", message={"content": "subtype compact_boundary",
                                                         "usage": {"input_tokens": 7}})])
        self.assertEqual(tr.context_stats("u1")["compactions"], 0)
        self.assertEqual(tr.compactions("u1"), [])

    def test_turns_unknown_without_turn_records(self):
        self.write("u1", [self.asst(1, 1, 1)])
        self.assertIsNone(tr.context_stats("u1")["turns"])

    def test_missing_transcript(self):
        self.assertIsNone(tr.context_stats("absent"))
        self.assertIsNone(tr.context_stats(None))
        self.assertEqual(tr.compactions(None), [])

    def test_compactions_in_order(self):
        self.write("u1", [self.boundary(10, 1, "2026-09-15T12:00:00Z"), self.asst(1, 1, 1),
                          self.boundary(20, 2, "2026-09-16T12:00:00Z")])
        self.assertEqual([(c["pre"], c["post"]) for c in tr.compactions("u1")], [(10, 1), (20, 2)])

if __name__ == "__main__":
    unittest.main()
