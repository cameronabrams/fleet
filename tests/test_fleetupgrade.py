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


class AttachedBackground(Upgrade):
    """A session /exit moved to the background, reattached in its pane: the pane runs
    `claude attach <id>` with no --name or --resume (observed 2026-09-15)."""
    def resolve(self, agent_list):
        from tests.test_agents import SAMPLE
        up = self.up
        with mock.patch.object(up, "sh", return_value="%1\t100\ttitle\t/home/u/work\tcoord\tcoord\t0\n"), \
             mock.patch.object(up, "claude_pid", return_value=("200", "claude attach b20bc72b")), \
             mock.patch.object(up, "agents", return_value=agent_list), \
             mock.patch.object(up, "foreign_claude", return_value=[("543137", "x"), ("543125", "y")]), \
             mock.patch.object(up, "uuid_from_descendants", return_value=None), \
             mock.patch.object(up, "proc_version", side_effect=lambda pid: "2.1.272"):
            return up.sessions()[0]

    def test_resolved_through_claude_agents_despite_shared_cwd(self):
        from tests.test_agents import SAMPLE
        s = self.resolve(SAMPLE)
        self.assertEqual((s["name"], s["resume_uuid"][:8], s["background"]), ("study", "b20bc72b", True))
        self.assertTrue(s["name_source"].startswith("verified"), s["name_source"])

    def test_unreadable_agents_is_unresolved_not_guessed(self):
        s = self.resolve(None)
        self.assertIn("UNRESOLVED", s["name_source"])
        self.assertIsNone(s["resume_uuid"])

    def test_attached_id(self):
        self.assertEqual(self.up.attached_id("claude attach b20bc72b"), "b20bc72b")
        self.assertIsNone(self.up.attached_id("claude --name x --resume b20bc72b-0000"))

class SessionDirectory(Upgrade):
    """The cd printed for a restart must be the SESSION's directory. os.getcwd() is
    the shell running the tool, which a `cd` in one of the session's own tool calls
    moves: on 2026-09-18 the hand-off said ~/.config/fleet for a session running in
    ~/.local/state/fleet, where --resume would have found no transcript."""
    def rows(self, pane_path="/home/u/somewhere-else", proc="/home/u/work"):
        with mock.patch.object(self.up, "sh", return_value=f"%1\t100\ttitle\t{pane_path}\tcoord\tcoord\t0\n"), \
             mock.patch.object(self.up, "claude_pid", return_value=("200", f"claude --name a --resume {U1}")), \
             mock.patch.object(self.up, "proc_cwd", side_effect=lambda pid: proc), \
             mock.patch.object(self.up, "agents", return_value=[]), \
             mock.patch.object(self.up, "foreign_claude", return_value=[]), \
             mock.patch.object(self.up, "uuid_from_descendants", return_value=None), \
             mock.patch.object(self.up, "proc_version", side_effect=lambda pid: "2.1.276"):
            return self.up.sessions()

    def test_row_cwd_comes_from_the_process_not_the_pane(self):
        self.assertEqual(self.rows()[0]["cwd"], "/home/u/work")

    def test_pane_path_is_the_fallback_when_proc_is_unreadable(self):
        self.assertEqual(self.rows(proc=None)[0]["cwd"], "/home/u/somewhere-else")

    def test_self_block_prints_the_sessions_directory(self):
        import contextlib, io
        ss = [{"name": "coord", "pane": "%1", "cwd": "/home/u/work", "pid": "200",
               "resume_uuid": U1, "version": "2.1.276", "ledger": True, "name_source": "verified"}]
        out = io.StringIO()
        with mock.patch.object(self.up, "proc_cwd", side_effect=lambda pid: "/home/u/work"), \
             mock.patch.object(self.up, "SELF_UUID", None), \
             mock.patch.object(os, "getcwd", return_value="/home/u/elsewhere"), \
             contextlib.redirect_stdout(out):
            self.up.self_block(ss)
        text = out.getvalue()
        self.assertIn("cd /home/u/work && ", text)
        self.assertNotIn("elsewhere", text)

class SessionLeaders(unittest.TestCase):
    """Reported by coord 2026-09-23: "Exit and stop tasks" does not stop a child
    that is its own session leader, so /exit never completes and the roll fails.
    Two sessions sat on 2.1.278 while nine rolled to 2.1.280."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.u = load_tool("fleetupgrade")

    def tearDown(self):
        self.cfg.close()

    def test_a_poll_loop_is_immortal_but_a_running_command_is_not(self):
        # Every Claude Code Bash command is a session leader, so the Ss signature
        # alone says only "this session is running something". Measured 2026-09-23:
        # both of these read as Ss, and only the first one blocks an exit.
        loop = ("/bin/bash -c eval 'until ! pgrep -f \"sqm -O\" >/dev/null; "
                "do sleep 30; done'")
        running = ("/bin/bash -c eval 'timeout 900 ssh picotte "
                   "apptainer pull --force htpolynet-cuda.sif'")
        self.assertTrue(self.u.immortal(loop))
        self.assertFalse(self.u.immortal(running))
        self.assertFalse(self.u.immortal("/bin/bash -c eval 'make -j8'"))
        self.assertTrue(self.u.immortal("bash -c while true; do sleep 5; done"))

    def test_the_tools_own_shell_is_never_reported(self):
        """This tool runs inside a Bash shell that IS a session leader and DOES
        poll if the command it is running says sleep. Without the ancestor
        exclusion, fleetupgrade reports the session it is run from."""
        mine = self.u._ancestors()
        self.assertIn(str(os.getpid()), mine)
        self.assertGreater(len(mine), 1)            # at least one real parent
        # every ancestor must be excluded, not just the immediate shell
        for pid in mine:
            self.assertTrue(os.path.exists("/proc/%s" % pid) or pid == "0")

    def test_the_tools_own_leader_shell_is_excluded_from_its_parents_subtree(self):
        """The shape that matters: claude -> bash -c (leader) -> this tool. Walking
        claude's descendants reaches that shell, and without the ancestor guard
        fleetupgrade reports the very session it was run from. `immortal` is forced
        true here so the guard under test is the only thing that can exclude it."""
        leader = parent = None
        pid = str(os.getpid())
        for _ in range(12):                      # climb to the first session leader
            st = self.u._stat(pid)
            if not st or st[1] == "0":
                break
            if pid == st[3]:
                leader, parent = pid, st[1]
                break
            pid = st[1]
        if not leader:
            self.skipTest("no session-leader ancestor in this runner")
        with mock.patch.object(self.u, "immortal", lambda c: True):
            found = {c["pid"] for c in self.u.leaders(parent)}
        self.assertNotIn(leader, found)

    def test_stat_parses_a_name_containing_spaces_and_parens(self):
        st = self.u._stat(os.getpid())
        self.assertIsNotNone(st)
        state, ppid, pgrp, sid = st
        self.assertTrue(state.isalpha())
        self.assertEqual(ppid, str(os.getppid()))
        self.assertTrue(sid.isdigit())

    def test_a_session_leader_child_is_found_and_an_ordinary_one_is_not(self):
        import subprocess, time
        plain = subprocess.Popen(["bash", "-c", "sleep 8"])
        leader = subprocess.Popen(["setsid", "bash", "-c", "sleep 8"])
        try:
            time.sleep(0.5)
            found = {c["pid"] for c in self.u.leaders(os.getpid())}
            # the setsid'd one is its own session; the plain one is in ours
            self.assertEqual(self.u._stat(leader.pid)[3], str(leader.pid))
            self.assertNotEqual(self.u._stat(plain.pid)[3], str(plain.pid))
            self.assertIn(str(leader.pid), found)
            self.assertNotIn(str(plain.pid), found)
        finally:
            for p in (plain, leader):          # by recorded pid, never by pattern
                p.kill(); p.wait()


class OtherTmuxSessions(unittest.TestCase):
    """A pane in another tmux session is not this fleet's, and must be reported
    rather than silently dropped: a fleet pane that lost its labels would
    otherwise vanish from a roll with no warning, which is the worse direction.
    """
    PANES = ("%1\t100\tcoord\t/home/u/work\tcoord\tcoord\t0\n"
             "%26\t200\tsidebar\t/home/u\t\t\tsidebar\n")

    def setUp(self):
        self.cfg = FakeConfig()
        self.up = load_tool("fleetupgrade")

    def tearDown(self):
        self.cfg.close()

    def rows(self):
        with mock.patch.object(self.up, "sh", return_value=self.PANES), \
             mock.patch.object(self.up, "claude_pid",
                               side_effect=lambda ppid: (str(int(ppid) + 1),
                                                         f"claude --name a --resume {U1}")), \
             mock.patch.object(self.up, "proc_cwd", side_effect=lambda pid: "/home/u/work"), \
             mock.patch.object(self.up, "agents", return_value=[]), \
             mock.patch.object(self.up, "foreign_claude", return_value=[]), \
             mock.patch.object(self.up, "uuid_from_descendants", return_value=None), \
             mock.patch.object(self.up, "proc_version", side_effect=lambda pid: "2.1.276"):
            return self.up.sessions()

    def test_the_unlabelled_pane_is_not_a_session_of_ours(self):
        rows = self.rows()
        self.assertEqual([r["pane"] for r in rows], ["%1"])

    def test_but_it_is_recorded_so_it_can_be_reported(self):
        self.rows()
        self.assertEqual([o["pane"] for o in self.up.OUTSIDE], ["%26"])
        self.assertEqual(self.up.OUTSIDE[0]["tmux_session"], "sidebar")

    def test_a_relabelled_pane_is_still_ours(self):
        """Only @fleet set, no @repo: a pane someone labelled by hand still counts."""
        self.PANES = "%26\t200\tx\t/home/u\t\trecords\tother\n"
        self.assertEqual([r["pane"] for r in self.rows()], ["%26"])
        self.assertEqual(self.up.OUTSIDE, [])


if __name__ == "__main__":
    unittest.main()
