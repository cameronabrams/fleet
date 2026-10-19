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

    def test_color_is_last_record(self):
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

    def test_polling_is_evidence_about_shape_not_about_being_stuck(self):
        """`immortal` still recognizes a poll loop, and that is now all it claims.

        It used to be the whole test for "this will block the roll", and the line
        this test replaces asserted that of these two, "only the first one blocks
        an exit". **Both block an exit.** `timeout 900 ssh` holds it for up to
        fifteen minutes, and on 2026-10-07 a 22-hour `eza` held one indefinitely
        with no sleep anywhere in it.

        Worse in the other direction: the loop below is the fleet's own documented
        way of waiting for a detached job correctly. Flagging it as stuck told a
        human to kill work that was proceeding exactly as instructed.
        """
        loop = ("/bin/bash -c eval 'until ! pgrep -f \"sqm -O\" >/dev/null; "
                "do sleep 30; done'")
        running = ("/bin/bash -c eval 'timeout 900 ssh picotte "
                   "apptainer pull --force sim-cuda.sif'")
        self.assertTrue(self.u.immortal(loop))
        self.assertFalse(self.u.immortal(running))
        self.assertFalse(self.u.immortal("/bin/bash -c eval 'make -j8'"))
        self.assertTrue(self.u.immortal("bash -c while true; do sleep 5; done"))

    def test_a_hung_command_with_no_sleep_is_still_a_blocker(self):
        """The false negative. `/exit` fails because a child is in its own process
        session, which a poll loop is one way to reach and not the definition.

        On 2026-10-07 `sim-study` was not flagged while a 22-hour-old `eza`
        -- an aliased `ls` that never returned -- held its exit. `notes-session` hit the
        identical hang the day before. Neither contains a sleep.
        """
        self.assertFalse(self.u.immortal("eza --group-directories-first"))
        self.assertTrue(self.u.blocks_exit("eza --group-directories-first"))
        self.assertTrue(self.u.blocks_exit("/bin/bash -c eval 'make -j8'"))

    def test_a_blocker_carries_its_age_and_whether_it_polls(self):
        """What a human needs to tell a 3-minute waiter from a 22-hour hang, in
        one look. The signature cannot distinguish them and neither can this tool;
        it reports the evidence instead of asserting a conclusion."""
        import subprocess, sys as _sys
        # Its own session leader AND still our child -- the exact shape the check
        # looks for, made on purpose rather than hoped for. The first version of
        # this test walked whatever happened to be running and asserted inside a
        # `for`, so an empty result passed it: removing both fields from the
        # record left it green. An empty iteration is not a satisfied assertion.
        kid = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"],
                               start_new_session=True)
        self.addCleanup(lambda: (kid.kill(), kid.wait()))
        found = self.u.leaders(os.getpid())
        self.assertTrue(found, "the planted child was not seen at all")
        c = next(x for x in found if x["pid"] == str(kid.pid))
        self.assertIsNotNone(c["age_s"])
        self.assertLess(c["age_s"], 60)
        self.assertFalse(c["polls"], "a bare sleep(30) in python is not a poll loop")

    def test_only_sessions_that_will_be_rolled_are_warned_about(self):
        """A blocker in a session nobody is about to `/exit` is noise at the one
        moment attention is scarce. Reported 2026-10-07: a session already on the
        new version, absent from the stale list, flagged anyway."""
        ss = [{"name": "stale-one", "version": "2.1.292", "pane": "%1",
               "leaders": [{"pid": "9", "cmd": "x", "age_s": 5, "polls": True}]},
              {"name": "already-new", "version": "2.1.293", "pane": "%2",
               "leaders": [{"pid": "8", "cmd": "y", "age_s": 5, "polls": True}]}]
        got = [x["name"] for x in self.u.blockers(ss, "2.1.293")]
        self.assertEqual(got, ["stale-one"])

    def test_blockers_are_ordered_oldest_first(self):
        """The 22-hour one is the one worth looking at, and it must not sort below
        a one-minute waiter."""
        ss = [{"name": "young", "version": "0", "pane": "%1",
               "leaders": [{"pid": "9", "cmd": "x", "age_s": 60, "polls": True}]},
              {"name": "old", "version": "0", "pane": "%2",
               "leaders": [{"pid": "8", "cmd": "y", "age_s": 80000, "polls": False}]}]
        self.assertEqual([x["name"] for x in self.u.blockers(ss, "9")],
                         ["old", "young"])

    def test_the_command_shown_is_the_one_a_human_can_read(self):
        """The output said "read each command before killing anything" and then
        printed the shell-snapshot preamble, truncating before the command. Advice
        the output makes impossible to follow is how a warning gets clicked past."""
        raw = ("/bin/bash -c source /home/u/.claude/shell-snapshots/snap-123.sh "
               "2>/dev/null || true && shopt -u extglob 2>/dev/null || true && "
               "{ \\builtin unalias -- 'unsetenv'; } >/dev/null 2>&1 || true && "
               "eval 'cd ~/devtests && J=$(cat run.pid); "
               "until ! kill -0 $J 2>/dev/null; do sleep 30; done'")
        # The harness appends this AFTER the closing quote, so a check anchored at
        # the end of the string never fires. Captured from a live pane 2026-10-07.
        raw += " < /dev/null && pwd -P >| /tmp/claude-2de3-cwd"
        got = self.u.spoken_cmd(raw)
        self.assertTrue(got.startswith("cd ~/devtests"), got)
        self.assertIn("until ! kill -0", got)
        self.assertNotIn("shell-snapshots", got)
        self.assertNotIn("pwd -P", got)
        self.assertFalse(got.endswith("'"), got)

    def test_a_command_with_no_preamble_is_left_alone(self):
        """The hung leaf case: `eza --group-directories-first` has no `eval` to
        strip, and returning an empty string would hide the one thing worth
        reading."""
        self.assertEqual(self.u.spoken_cmd("eza --group-directories-first"),
                         "eza --group-directories-first")

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
    # pane_id, pane_pid, pane_title, pane_current_path, @agent, session_name
    PANES = ("%1\t100\tcoord\t/home/u/work\tcoord\t0\n"
             "%26\t200\tsidebar\t/home/u\t\tsidebar\n")

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

    def test_a_pane_labelled_by_hand_is_ours(self):
        """A pane in another tmux session that carries `@agent` counts, whoever
        set it. Membership is the label, never the tmux session it sits in."""
        self.PANES = "%26\t200\tx\t/home/u\trecords\tother\n"
        self.assertEqual([r["pane"] for r in self.rows()], ["%26"])
        self.assertEqual(self.up.OUTSIDE, [])


if __name__ == "__main__":
    unittest.main()


def sess(name="alpha", version="2.1.298", **kw):
    """A `sessions()` row, with every field the eligibility gates read."""
    d = {"name": name, "version": version, "resume_uuid": U1, "background": False,
         "name_source": "verified: --resume in argv", "leaders": [],
         "ledger": "/s/rearm/%s.md" % name, "pane": "%1", "pid": "1",
         "cwd": CWD, "color": "red"}
    d.update(kw)
    return d


class EveryGateIsARefusal(unittest.TestCase):
    """`--eligible` decides who must NOT be rolled. It never rolls anything.

    The direction is the whole design. A gate that cannot be evaluated must
    refuse, because the alternative -- an unreadable source reading as clearance
    -- is this repository's oldest catalogued failure, and it is far more
    dangerous here than on a board: a board that fails toward reassurance shows a
    wrong color, a roll that fails toward reassurance restarts a session that was
    holding something.

    Spec: `coord-autoroll-spec-20261015.md`, 2026-10-15.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.up = load_tool("fleetupgrade")

    def tearDown(self):
        self.cfg.close()

    def judge(self, s, inst="2.1.300", agents={"alpha": "idle"},
              watch={"cluster_ok": True, "jobs": []}, pinned=(), hold=None,
              soak=24, lag=2, age=48.0, self_uuid=U2):
        rows = self.up.eligibility([s], inst, agents, watch, list(pinned), hold,
                                   soak_hours=soak, lag=lag, age_hours=age,
                                   self_uuid=self_uuid)
        return rows[0][1]

    # -- the sources that can fail -------------------------------------------

    def test_an_unreadable_agents_list_refuses_everyone(self):
        """`claude agents` is the only source for busy/idle. Without it the gate
        has no answer, and no answer is not yes."""
        why = self.judge(sess(), agents=None)
        self.assertTrue(any("could not be read" in w for w in why), why)

    def test_a_session_the_agents_list_does_not_mention_refuses(self):
        why = self.judge(sess(name="ghost"), agents={"alpha": "idle"})
        self.assertIn("not listed by `claude agents`", why)

    def test_a_failed_cluster_query_refuses_everyone(self):
        """`fleetwatch` prints a banner and exits 0 when its query fails, so an
        empty job list is also what a broken query looks like. A restart decided
        on that kills a watcher the asker could not see."""
        for w in ({"cluster_ok": False, "jobs": []}, None, {}):
            why = self.judge(sess(), watch=w)
            self.assertTrue(any("runtime is unknown" in x for x in why), (w, why))

    def test_no_soaked_release_refuses_everyone(self):
        """What the on-disk window now gates: the TARGET, not who may roll.

        Before 2026-10-17 it refused each session for the newest release being
        young -- and since releases land about every 25 hours against a 24-hour
        window, that refused everyone almost always. Two fires, two days, zero
        eligible. The window now chooses which release to roll TO, and only the
        absence of any soaked release refuses anybody.
        """
        why = self.judge(sess(), inst=None)
        self.assertTrue(any("no soaked release" in w for w in why), why)

    def test_the_newest_release_being_young_refuses_nobody(self):
        """The defect itself, as a test. `age` is the newest release's age; with
        a target in hand it must not bear on eligibility at all."""
        self.assertEqual(self.judge(sess(), age=3.0), [])
        self.assertEqual(self.judge(sess(), age=None), [])

    def test_an_unknown_running_version_still_refuses(self):
        self.assertIn("its running version is unknown", self.judge(sess(version=None)))

    # -- the gates themselves -------------------------------------------------

    def test_a_busy_session_is_not_eligible(self):
        self.assertIn("status is busy", self.judge(sess(), agents={"alpha": "busy"}))

    def test_the_on_disk_window_no_longer_refuses_a_session(self):
        """It picks the target instead. Kept as the gravestone of the gate that
        could not open: a per-session refusal keyed on the newest release's age is
        a refusal keyed on something that resets every 25 hours."""
        for age in (48.0, 3.0, None):
            self.assertEqual(self.judge(sess(), age=age), [], age)

    def test_a_single_release_is_skipped_at_the_default_lag(self):
        self.assertTrue(any("1 version behind" in w
                            for w in self.judge(sess(version="2.1.299"))))
        self.assertEqual(self.judge(sess(version="2.1.298")), [])
        self.assertEqual(self.judge(sess(version="2.1.299"), lag=1), [])

    def test_a_session_already_current_has_nothing_to_do(self):
        self.assertIn("already on 2.1.300", self.judge(sess(version="2.1.300")))

    def test_an_exit_blocking_child_is_skipped_and_never_killed(self):
        """The spec's hardest rule. Separating a hang from work in progress means
        reading the command, which is a judgement; the automation's only correct
        move is to leave the session alone."""
        why = self.judge(sess(leaders=[{"pid": "99", "cmd": "uv run thing.py",
                                        "age_s": 90.0, "polls": False}]))
        self.assertTrue(any("never killed" in w for w in why), why)
        self.assertTrue(any("pid 99" in w for w in why), why)

    def test_live_runtime_without_a_ledger_refuses(self):
        w = {"cluster_ok": True, "jobs": [{"job": "1", "watched_by": ["alpha"]}]}
        self.assertIn("holds live cluster work and has no re-arm ledger",
                      self.judge(sess(ledger=None), watch=w))
        self.assertEqual(self.judge(sess(), watch=w), [],
                         "a ledger naming what to re-arm is what the spec asks for")

    def test_a_watcher_part_way_through_its_set_counts_as_runtime(self):
        w = {"cluster_ok": True, "jobs": [],
             "watchers_partway": [{"session": "alpha", "job": "7"}]}
        self.assertIn("holds live cluster work and has no re-arm ledger",
                      self.judge(sess(ledger=None), watch=w))

    # -- structural refusals, which are not in the spec ------------------------

    def test_a_backgrounded_session_is_never_rolled(self):
        """`/exit` can background a session (2.1.272): the pid goes and a fork
        continues under a NEW session id, so resuming the old uuid starts a SECOND
        live session on a forked history. `fleetupgrade` warns a human about this;
        an unattended driver gets no warnings."""
        why = self.judge(sess(background=True))
        self.assertTrue(any("fork" in w for w in why), why)

    def test_an_unresolved_resume_uuid_is_never_rolled(self):
        why = self.judge(sess(name_source="UNRESOLVED: two claudes share this cwd"))
        self.assertTrue(any("guess" in w for w in why), why)

    def test_no_resume_uuid_means_nothing_to_resume(self):
        self.assertIn("no resume uuid, so there is nothing to resume",
                      self.judge(sess(resume_uuid=None)))

    # -- the asker ------------------------------------------------------------

    def test_the_asking_session_cannot_roll_itself(self):
        """By uuid, not by name. The name of whichever session drives the roll is
        configuration, not something this repository may know."""
        why = self.judge(sess(), self_uuid=U1)
        self.assertIn("this is the session asking; it cannot roll itself", why)
        self.assertEqual(self.judge(sess(), self_uuid=U2), [])

    def test_an_unknown_asker_refuses_everyone(self):
        """The same rule as every other source that fails here, and the one most
        easily missed, because the gap is invisible from inside: with no uuid the
        driving session's only remaining exclusion is "status is busy" -- true
        merely because running the tool made it busy. A driver that is not the
        session it is reading about would see that session eligible and roll the
        thing it is running in.

        Reported by coord 2026-10-15 from the JSON, where the banner that says
        this in the text report does not reach.
        """
        why = self.judge(sess(), self_uuid=None)
        self.assertTrue(any("could not be identified" in w for w in why), why)
        self.assertTrue(any("nothing is self-excluded" in w for w in why), why)

    def test_a_busy_asker_is_not_what_excludes_it(self):
        """The incidental exclusion, named so it cannot be mistaken for the real
        one. An idle asker must still be refused when the uuid is missing."""
        why = self.judge(sess(), self_uuid=None, agents={"alpha": "idle"})
        self.assertNotEqual(why, [], "an idle session passed with no asker known")

    # -- reasons accumulate ----------------------------------------------------

    def test_every_reason_is_reported_not_just_the_first(self):
        """A skip that says only "not eligible" teaches nobody anything, and the
        list is the whole value of the report -- to the driver, and to whoever is
        later deciding whether the gates are set right."""
        why = self.judge(sess(version="2.1.299", background=True),
                         agents={"alpha": "busy"},
                         self_uuid=U1, hold="held by hand")
        self.assertGreaterEqual(len(why), 4, why)


class TheJsonCarriesWhoAsked(unittest.TestCase):
    """A driver must be able to ASSERT self-exclusion, not grep for it.

    The reason lands in the asking session's own row -- which is only findable by
    a driver that already knows which row is its own, the very thing the field
    exists to tell it. The text report shouts it in a banner; the JSON had no
    equivalent until coord said so on 2026-10-15, having gone looking for it.
    """
    def test_the_field_is_top_level_and_nullable(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetupgrade")).read()
        body = src[src.index("def report_eligible"):src.index("def main():")]
        self.assertIn('"asking": SELF_UUID or None', body,
                      "a --json driver cannot tell whether anything was self-excluded")
        # Before the per-session rows, so it is read before the list it qualifies.
        self.assertLess(body.index('"asking"'), body.index('"sessions"'))


class TheHoldFileIsADeclaration(unittest.TestCase):
    """What replaces the fleet's owner as the per-roll gate: a standing refusal, written
    once, rather than a decision taken again every time."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.up = load_tool("fleetupgrade")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cfg.close)

    def hold(self, body=None):
        p = os.path.join(self.tmp.name, "no-roll")
        if body is not None:
            with open(p, "w") as f:
                f.write(body)
        return self.up.hold_file(p)

    def test_no_file_holds_nothing(self):
        self.assertEqual(self.hold(), ([], None))

    def test_an_empty_file_holds_everything(self):
        pinned, why = self.hold("")
        self.assertIsNone(pinned)
        self.assertIn("all rolling is held", why)
        self.assertIsNone(self.hold("  \n\n # just a comment\n")[0])

    def test_named_versions_are_refused_as_targets(self):
        pinned, why = self.hold("2.1.300   # monitors expire early\n")
        self.assertEqual(pinned, ["2.1.300"])
        self.assertIsNone(why)
        rows = self.up.eligibility([sess()], "2.1.300", {"alpha": "idle"},
                                   {"cluster_ok": True, "jobs": []}, pinned, why,
                                   age_hours=48.0, lag=1, self_uuid=U2)
        self.assertTrue(any("pinned out" in w for w in rows[0][1]), rows[0][1])

    def test_a_file_that_cannot_be_read_holds(self):
        """It was put there to stop something. A read error is not permission."""
        p = os.path.join(self.tmp.name, "no-roll")
        with open(p, "w") as f:
            f.write("2.1.300")
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o644)
        if os.access(p, os.R_OK):
            self.skipTest("running as a user that ignores file modes")
        pinned, why = self.up.hold_file(p)
        self.assertIsNone(pinned)
        self.assertIn("could not be read", why)


class CountingReleases(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.up = load_tool("fleetupgrade")
        self.addCleanup(self.cfg.close)

    def test_patch_distance_within_one_minor(self):
        self.assertEqual(self.up.version_lag("2.1.296", "2.1.300"), 4)
        self.assertEqual(self.up.version_lag("2.1.300", "2.1.300"), 0)

    def test_a_different_minor_is_uncountable_not_zero(self):
        """None means "behind by an amount this cannot count", and the caller
        treats it as satisfying any lag -- a minor change is a bigger step than
        any patch distance, not a smaller one. Reading None as 0 would hold back
        exactly the roll most worth making."""
        self.assertIsNone(self.up.version_lag("2.1.300", "2.2.0"))
        self.assertIsNone(self.up.version_lag("2.1.300", "3.0.0"))
        rows = self.up.eligibility([sess(version="2.1.300")], "2.2.0",
                                   {"alpha": "idle"}, {"cluster_ok": True, "jobs": []},
                                   [], None, age_hours=48.0, lag=9, self_uuid=U2)
        self.assertEqual(rows[0][1], [], "an uncountable lag must satisfy any lag")

    def test_unparseable_and_missing_are_none(self):
        for a, b in (("dev", "2.1.300"), ("2.1.300", "dev"), (None, "2.1.300"),
                     ("2.1.300", None), ("2.1", "2.1.300")):
            self.assertIsNone(self.up.version_lag(a, b), (a, b))


class EligibleReportsAndDoesNotAct(unittest.TestCase):
    """`fleetupgrade`'s docstring promises it never restarts anything. `--eligible`
    is the first thing in it that computes an INTENTION, which is where that
    promise is easiest to lose -- not by someone deciding to break it, but by a
    helper growing one convenient call.

    Checked on the parsed syntax, not on the text. The first version of this
    grepped for "kill" over the source and failed on four comments and a line of
    output that all say it never kills -- convicting the innocent, which is the
    documented way a check stops being read (checks-that-reassure.md).
    """
    FUNCS = ("hold_file", "version_lag", "installed_age_hours", "runtime_owners",
             "eligibility", "_leader_label", "_opt", "gather_eligibility",
             "run_json", "report_eligible")

    def setUp(self):
        import ast
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetupgrade")).read()
        tree = ast.parse(src)
        self.ast = ast
        self.defs = {n.name: n for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name in self.FUNCS}

    def test_every_function_in_the_path_was_found(self):
        """Or the two tests below pass by looking at nothing, which is how a
        structural check quietly stops covering the thing it names."""
        self.assertEqual(sorted(self.defs), sorted(self.FUNCS))

    def calls(self, name):
        return [n for n in self.ast.walk(self.defs[name])
                if isinstance(n, self.ast.Call)]

    def test_nothing_in_the_path_launches_a_process_except_run_json(self):
        for fn in self.FUNCS:
            if fn == "run_json":
                continue
            for c in self.calls(fn):
                src = self.ast.unparse(c.func)
                self.assertNotIn("subprocess", src, "%s() launches a process" % fn)
                self.assertNotIn("popen", src.lower(), "%s() launches a process" % fn)
                self.assertNotEqual(src, "sh", "%s() shells out" % fn)
                self.assertNotEqual(src, "tmux", "%s() drives tmux" % fn)
                self.assertNotIn("os.kill", src, "%s() signals a process" % fn)

    def test_the_one_command_it_runs_is_a_sibling_report(self):
        """A report asking a report. `fleetwatch --json` changes nothing, and it
        is the only argv this path ever builds."""
        argvs = [self.ast.unparse(c.args[0]) for fn in self.FUNCS
                 for c in self.calls(fn)
                 if self.ast.unparse(c.func) == "run_json" and c.args]
        self.assertEqual(argvs, ["['fleetwatch', '--json']"])

    def test_the_computation_itself_touches_nothing_at_all(self):
        """`eligibility` is pure over its arguments: every source is passed in, so
        the gates are testable without a fleet, and so nothing can be read at the
        moment of deciding that was not read at the moment of reporting."""
        for c in self.calls("eligibility"):
            src = self.ast.unparse(c.func)
            self.assertFalse(src.startswith("os.") or src.startswith("open"),
                             "eligibility() reads %s; its inputs must be arguments" % src)
