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


class LastVersion(Transcripts):
    """Every record a session writes carries the version of the process that wrote
    it. That is the per-process truth when the binary cannot say (replaced in place
    since launch), and it is read from the tail: transcripts run to tens of MB."""
    def test_last_record_wins(self):
        self.write("u1", [rec(type="user", version="2.1.270"),
                          rec(type="assistant", version="2.1.284", message={"content": []})])
        self.assertEqual(tr.last_version("u1"), "2.1.284")

    def test_no_version_no_transcript(self):
        self.write("u2", [rec(type="user")])
        self.assertIsNone(tr.last_version("u2"))
        self.assertIsNone(tr.last_version("nope"))
        self.assertIsNone(tr.last_version(None))


class ParkedSuccessor(Transcripts):
    """Claude Code can PARK an idle interactive session onto a daemon job: the
    process's registry entry (~/.claude/sessions/<pid>.json) gains `parkedJobId`,
    a sibling entry carries that `jobId` with the NEW sessionId, and the new
    transcript holds every record of the old one plus everything after. argv, the
    scratchpad path and "first record after launch" all still name the OLD file,
    because a fork copies old timestamps. OBSERVED 2026-09-28: `/color` landed in
    the successor while the manifest read `verified` for the predecessor."""
    def setUp(self):
        super().setUp()
        self.reg = tempfile.TemporaryDirectory()
        self.rp = mock.patch.object(tr, "SESSIONS", self.reg.name)
        self.rp.start()

    def tearDown(self):
        self.rp.stop(); self.reg.cleanup(); super().tearDown()

    def entry(self, pid, **kw):
        with open(os.path.join(self.reg.name, f"{pid}.json"), "w") as f:
            json.dump({"pid": pid, "cwd": "/home/u/work", **kw}, f)

    def proc(self):
        return {"pid": 27309, "resume_uuid": "old", "argv": ["claude", "--resume", "old"]}

    def test_parked_session_resumes_the_successor(self):
        self.write("old", [rec(type="user", agentName="alpha")], time.time() - 600)
        self.write("new", [rec(type="user", agentName="alpha"), rec(type="agent-color", agentColor="blue")])
        self.entry(27309, sessionId="old", kind="interactive", parkedJobId="new")
        self.entry(19885, sessionId="new", kind="bg", jobId="new")
        uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual(uuid, "new")
        self.assertTrue(how.startswith("verified: parked"), how)
        self.assertIn("old", how)

    def test_parked_but_successor_transcript_missing_is_unverified(self):
        self.write("old", [rec(type="user", agentName="alpha")])
        self.entry(27309, sessionId="old", kind="interactive", parkedJobId="gone")
        self.entry(19885, sessionId="gone", kind="bg", jobId="gone")
        uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual(uuid, "old")
        self.assertTrue(how.startswith("UNVERIFIED"), how)

    def test_parked_job_with_no_registry_sibling_is_unverified(self):
        self.write("old", [rec(type="user", agentName="alpha")])
        self.entry(27309, sessionId="old", kind="interactive", parkedJobId="nobody")
        uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual(uuid, "old")
        self.assertTrue(how.startswith("UNVERIFIED"), how)

    def test_sibling_in_another_directory_is_not_the_successor(self):
        self.write("old", [rec(type="user", agentName="alpha")])
        self.write("new", [rec(type="user", agentName="alpha")])
        self.entry(27309, sessionId="old", kind="interactive", parkedJobId="new")
        with open(os.path.join(self.reg.name, "19885.json"), "w") as f:
            json.dump({"pid": 19885, "cwd": "/home/u/elsewhere", "sessionId": "new", "jobId": "new"}, f)
        uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual(uuid, "old")
        self.assertTrue(how.startswith("UNVERIFIED"), how)

    def test_unparked_session_is_unchanged(self):
        self.write("old", [rec(type="user", agentName="alpha")])
        self.entry(27309, sessionId="old", kind="interactive")
        with mock.patch.object(tr, "cleared_successor", return_value=(None, 0)):
            uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual((uuid, how), ("old", "verified: --resume in process argv, no /clear since launch"))

    def test_no_registry_entry_is_unchanged(self):
        self.write("old", [rec(type="user", agentName="alpha")])
        with mock.patch.object(tr, "cleared_successor", return_value=(None, 0)):
            uuid, how = tr.resume_handle(self.proc(), "/home/u/work", "alpha")
        self.assertEqual(uuid, "old")
        self.assertTrue(how.startswith("verified"), how)
