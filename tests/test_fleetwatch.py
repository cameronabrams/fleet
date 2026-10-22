import re
import contextlib, datetime, io, json, os, subprocess, sys, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.w = load_tool("fleetwatch")

    def tearDown(self):
        self.cfg.close()


class Owners(Base):
    def test_first_match_wins(self):
        self.assertEqual(self.w.owner_of("/scratch/proj-a-sweep/run1"), "alpha-runs")
        self.assertEqual(self.w.owner_of("/scratch/proj-a/build"), "alpha")

    def test_unmatched_is_never_guessed(self):
        self.assertEqual(self.w.owner_of("/scratch/other"), "UNATTRIBUTED")


SQUEUE_OK = """\
23225789|PENDING|JobHeldUser|2
23330046|RUNNING|None|3
23330046|PENDING|Priority|4
--WD--
23225789|/scratch/proj-a-sweep/ex17
23330046|/scratch/elsewhere
--END--
"""

class LiveJobs(Base):
    def jobs(self, out):
        with mock.patch.object(self.w, "sh", return_value=out):
            return self.w.live_jobs()

    def test_parses_tasks_states_owner_and_held(self):
        jobs, ok, _res = self.jobs(SQUEUE_OK)
        self.assertTrue(ok)
        self.assertEqual(jobs["23225789"]["tasks"], 2)
        self.assertTrue(jobs["23225789"]["held"])
        self.assertEqual(jobs["23225789"]["owner"], "alpha-runs")
        j = jobs["23330046"]
        self.assertEqual((j["tasks"], j["states"]), (7, {"RUNNING": 3, "PENDING": 4}))
        self.assertFalse(j["held"])          # Priority starts on its own: needs a watcher
        self.assertEqual(j["owner"], "UNATTRIBUTED")

    def test_failed_ssh_is_not_no_work(self):
        # a banner and nothing else: must read as a FAILED query, not an empty queue
        jobs, ok, _res = self.jobs("Welcome to the cluster\n")
        self.assertEqual(jobs, {})
        self.assertFalse(ok)

    def test_empty_queue_is_ok(self):
        self.assertEqual(self.jobs("--WD--\n--END--\n"), ({}, True, ""))

    def test_final_states(self):
        with mock.patch.object(self.w, "sh", return_value="1|COMPLETED,\n2|\n--END--\n"):
            self.assertEqual(self.w.final_states({"1", "2"}), {"1": {"COMPLETED"}, "2": set()})
        with mock.patch.object(self.w, "sh", return_value=""):
            self.assertIsNone(self.w.final_states({"1"}))
        self.assertEqual(self.w.final_states(set()), {})


def starttime(pid):
    raw = open(f"/proc/{pid}/stat").read()
    return raw[raw.rindex(")") + 2:].split()[19]

class Alive(Base):
    def test_live_process_with_matching_identity(self):
        me = os.getpid()
        self.assertTrue(self.w.alive(me))
        self.assertTrue(self.w.alive(me, starttime(me)))

    def test_reused_pid_is_not_alive(self):
        self.assertFalse(self.w.alive(os.getpid(), "1"))

    def test_gone_pid(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
        self.assertFalse(self.w.alive(p.pid))

    def test_zombie_is_not_alive(self):
        # kill -0 succeeds on a zombie; alive() must not
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        for _ in range(100):
            try:
                if open(f"/proc/{p.pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z":
                    break
            except OSError:
                break
            import time; time.sleep(0.02)
        os.kill(p.pid, 0)                       # addressable ...
        self.assertFalse(self.w.alive(p.pid))  # ... but not alive
        p.wait()


class Registered(Base):
    def reg(self, **r):
        d = os.path.join(self.cfg.state, "watchers"); os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{r['session']}-{r['job']}-{r['pid']}.json")
        json.dump(r, open(path, "w"))
        return path

    def test_live_dead_and_legacy(self):
        me = os.getpid()
        self.reg(session="alpha", job="111111", pid=me, starttime=starttime(me))
        self.reg(session="beta", job="222222", pid=me, starttime="1")         # reused pid
        self.reg(session="gamma", job="333333", pid=me)                       # no starttime
        live, dead, _ = self.w.registered()
        self.assertEqual(live, {"alpha": {"111111"}})
        self.assertEqual(sorted(r["session"] for r in dead), ["beta", "gamma"])


class AWatcherPartWayThroughItsSet(Base):
    """One watcher, several jobs. The first to finish must not read as a fault.

    A registration is one file per (session, job, pid), so a watcher polling three
    jobs is three rows sharing a pid -- the registry models this correctly. The
    stale check did not: it asked only "is this job in squeue", so the first job of
    a set to finish produced

        !! WATCHER ON WORK THAT IS NO LONGER LIVE -- the monitor will not exit
           if its completion test cannot close. Check it.

    while the watcher was alive and legitimately polling the other two. The
    diagnosis is wrong in both halves: the monitor WILL exit, and there is nothing
    to check. Observed 2026-10-06 on sweep-session, pid 645241 over
    26433958/59/60, after 26433960 completed.

    The advice is worse than the alarm. `fleetregister --clear` refuses while the
    pid is alive -- correctly -- and says "stop the watcher first", which here
    would forfeit the nudge for the two jobs still running. The one remedy named
    is the one thing nobody should do.
    """
    def reg(self, **r):
        d = os.path.join(self.cfg.state, "watchers"); os.makedirs(d, exist_ok=True)
        json.dump(r, open(os.path.join(
            d, f"{r['session']}-{r['job']}-{r['pid']}.json"), "w"))

    def setUp(self):
        super().setUp()
        me = os.getpid()
        for j in ("111111", "222222", "333333"):
            self.reg(session="sweep", job=j, pid=me, starttime=starttime(me))
        self.me = me

    def test_the_pid_behind_each_registration_is_available(self):
        """The stale check could not have known: `registered()` returned
        session -> {jobs} and dropped the pid, so "same watcher" was not a
        question it was able to ask."""
        live, dead, by_job = self.w.registered()
        self.assertEqual(live, {"sweep": {"111111", "222222", "333333"}})
        self.assertEqual(by_job[("sweep", "111111")], self.me)
        self.assertEqual(by_job[("sweep", "333333")], self.me)

    def test_a_finished_job_whose_watcher_still_has_live_work_is_not_stale(self):
        live, dead, by_job = self.w.registered()
        jobs = {"111111": {}, "222222": {}}          # 333333 has completed
        stale, partway = self.w.split_stale(live, by_job, jobs)
        self.assertEqual(stale, [], "a watcher mid-set is not a fault")
        self.assertEqual(len(partway), 1)
        self.assertEqual(partway[0]["job"], "333333")
        self.assertEqual(sorted(partway[0]["still_watching"]), ["111111", "222222"])

    def test_the_last_job_of_the_set_is_stale_again(self):
        """When nothing the watcher covers is live any more, the original alarm is
        the right one: that is a monitor whose completion test may not close."""
        live, dead, by_job = self.w.registered()
        stale, partway = self.w.split_stale(live, by_job, {})
        self.assertEqual(partway, [])
        self.assertEqual(sorted(x["job"] for x in stale),
                         ["111111", "222222", "333333"])

    def test_two_watchers_of_one_session_do_not_cover_for_each_other(self):
        """`still_watching` is keyed on the PID, not the session. A session with a
        healthy watcher on job B and a dead-ended one on job A would otherwise
        have its real problem hidden by the healthy one.

        The second watcher must be genuinely LIVE on a LIVE job. The first version
        of this test registered it against a dead pid, which `registered()` drops
        before `split_stale` ever sees it -- so the session-wide-vouching bug it
        was written to catch passed it. It asserted the right thing about a case
        that could not produce the bug.
        """
        import subprocess, sys as _sys
        other = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (other.kill(), other.wait()))
        self.reg(session="sweep", job="444444", pid=other.pid,
                 starttime=starttime(other.pid))
        live, dead, by_job = self.w.registered()
        self.assertEqual(by_job[("sweep", "444444")], other.pid,
                         "the second watcher must be live, or this proves nothing")
        stale, partway = self.w.split_stale(live, by_job, {"444444": {}})
        self.assertEqual(partway, [], "a different pid is a different watcher")
        self.assertEqual(len(stale), 3)


class Watchers(Base):
    def test_one_shot_mention_is_not_a_watcher(self):
        # Evidence of a poll LOOP is required: a command that merely names the job is not.
        loop = "bash -c while true; do sacct -j 23472564; sleep 300; done"
        once = "bash -c sacct -j 23472564 -X"
        self.assertEqual(self.w.polled_jobs(loop), {"23472564"})
        self.assertEqual(self.w.polled_jobs(once), set())
        self.assertEqual(self.w.polled_jobs("sleep 60"), set())

class Delivery(Base):
    """The delivery half: nudges that never reached a session.

    Every test here is written so that it fails when the guard is removed. The
    ones that matter most are the two about ABSENCE -- an unreadable log and an
    unparseable line -- because those are the paths on which "no rows" would
    otherwise be produced by the check breaking rather than by nothing being wrong.
    """
    def write(self, *recs):
        path = os.path.join(self.cfg.state, "nudges.log")
        with open(path, "w") as f:
            for r in recs:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
        return path

    def rec(self, ago_h=1, **kw):
        t = (datetime.datetime.now(datetime.timezone.utc).astimezone()
             - datetime.timedelta(hours=ago_h))
        r = dict(time=t.strftime("%Y-%m-%dT%H:%M:%S%z"), session="alpha",
                 job="111111", text="job done")
        r.update(kw)
        return r

    def test_absent_log_is_quiet(self):
        # no nudge was ever sent: fleetnudge creates the log on first use
        h = self.w.nudge_holes()
        self.assertEqual((h["silent"], h["pushed"], h["unreadable"]), ([], [], None))

    def test_muted_push_is_the_alarm_and_a_sent_push_is_not(self):
        self.write(self.rec(outcome="not delivered", reason="pane busy",
                            push="push muted (/home/x/ntfy-off exists)"),
                   self.rec(job="222222", outcome="not delivered", reason="pane busy",
                            push="push sent (HTTP 200)"))
        h = self.w.nudge_holes()
        self.assertEqual([r["job"] for r in h["silent"]], ["111111"])
        self.assertEqual([r["job"] for r in h["pushed"]], ["222222"])

    def test_delivered_and_waiting_are_not_holes(self):
        self.write(self.rec(outcome="delivered", pane="%1"),
                   self.rec(outcome="waiting", reason="mid-turn"),
                   self.rec(outcome="delivered", pane="%1"))
        h = self.w.nudge_holes()
        self.assertEqual((h["silent"], h["pushed"], h["dangling"]), ([], [], []))

    def test_unrecorded_push_reads_as_nobody_told(self):
        # a record with no push field at all: unknown must fail toward the alarm
        self.write(self.rec(outcome="not delivered", reason="pane busy"))
        self.assertEqual(len(self.w.nudge_holes()["silent"]), 1)
        self.assertFalse(self.w._reached_phone({"push": "push FAILED: timed out"}))
        self.assertFalse(self.w._reached_phone({"push": "push sent (HTTP 503)"}))
        self.assertTrue(self.w._reached_phone({"push": "push sent (HTTP 200)"}))

    def test_a_later_delivery_annotates_but_does_not_suppress(self):
        # 2026-09-17: 13:22 lost, 14:44 re-sent and delivered. The lost line still
        # carried its own message, so it stays listed -- with the later one named.
        self.write(self.rec(ago_h=3, outcome="not delivered", reason="corrupt input line",
                            push="push muted (x exists)"),
                   self.rec(ago_h=2, outcome="delivered", pane="%1"))
        h = self.w.nudge_holes()
        self.assertEqual(len(h["silent"]), 1)
        self.assertTrue(h["silent"][0]["_later"])
        # and a hole with nothing after it is not annotated
        self.write(self.rec(ago_h=3, outcome="not delivered", reason="x",
                            push="push muted (x exists)"))
        self.assertIsNone(self.w.nudge_holes()["silent"][0]["_later"])

    def test_dangling_waiting_only_when_old_enough(self):
        # a retry loop still going logs 'waiting' and is perfectly healthy
        self.write(self.rec(ago_h=0, outcome="waiting", reason="alpha is mid-turn"))
        self.assertEqual(self.w.nudge_holes()["dangling"], [])
        # one this old was killed before it could deliver, give up, or push
        self.write(self.rec(ago_h=5, outcome="waiting", reason="alpha is mid-turn"))
        self.assertEqual(len(self.w.nudge_holes()["dangling"]), 1)
        # unless an outcome followed it
        self.write(self.rec(ago_h=5, outcome="waiting", reason="alpha is mid-turn"),
                   self.rec(ago_h=4, outcome="delivered", pane="%1"))
        self.assertEqual(self.w.nudge_holes()["dangling"], [])

    def test_unreadable_log_is_reported_not_treated_as_clean(self):
        path = self.write(self.rec(outcome="not delivered", reason="x", push="push muted (y)"))
        os.chmod(path, 0o000)
        try:
            h = self.w.nudge_holes()
        finally:
            os.chmod(path, 0o644)
        if os.geteuid() == 0:
            self.skipTest("running as root: chmod cannot make a file unreadable")
        self.assertIsNotNone(h["unreadable"])
        self.assertEqual(h["silent"], [])          # and the section says so out loud

    def test_unparseable_lines_are_counted_not_skipped(self):
        self.write("{not json", json.dumps({"session": "alpha", "outcome": "not delivered"}),
                   self.rec(outcome="delivered", pane="%1"))
        h = self.w.nudge_holes()
        self.assertEqual(h["bad_lines"], 2)        # the junk, and the one with no time

    def test_window_hides_nothing_silently(self):
        self.write(self.rec(ago_h=24 * 30, outcome="not delivered", reason="old",
                            push="push muted (x)"))
        h = self.w.nudge_holes()
        self.assertEqual((h["silent"], h["older"]), ([], 1))

    def test_session_filter(self):
        self.write(self.rec(outcome="not delivered", reason="x", push="push muted (y)"),
                   self.rec(session="beta", outcome="not delivered", reason="x",
                            push="push muted (y)"))
        self.assertEqual([r["session"] for r in self.w.nudge_holes("alpha")["silent"]], ["alpha"])
        self.assertEqual(len(self.w.nudge_holes()["silent"]), 2)

    def test_quarantined_mail_is_counted_so_an_empty_section_is_not_all_clear(self):
        # mail that never became a nudge cannot appear in nudges.log at all
        with open(os.path.join(self.cfg.state, "mail-delivered.json"), "w") as f:
            json.dump({"mail/a.md": {"outcome": "quarantined", "reason": "asks for a push"},
                       "mail/b.md": {"outcome": "delivered", "nudged": False},
                       "mail/c.md": {"outcome": "delivered", "nudged": True}}, f)
        self.assertEqual(self.w.nudge_holes()["mail_stuck"], 2)

    def test_mail_from_is_shown_on_a_hole(self):
        self.write(self.rec(outcome="not delivered", reason="x", push="push muted (y)",
                            mail_from="other-fleet/coord"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.print_delivery(self.w.nudge_holes())
        self.assertIn("mail from other-fleet/coord", out.getvalue())
        self.assertIn("NUDGE NEVER ARRIVED", out.getvalue())


class ANudgeNotDeliveredIsNotAlwaysNewsLost(Base):
    """"A nudge never arrived and no push went out" was 2/3 false on 2026-10-15.

    The classifier bucketed on `outcome` alone. Two of the three rows driving it
    were `fleetnudge` DECLINING because it was running inside the session it would
    have typed into -- an in-session task that already notifies it. Nothing was
    lost; the board called it a delivery hole, and a board that invents holes gets
    read past, which costs the real ones.

    **Exit code cannot carry the distinction.** The decline is code 2, shared with
    caller errors that genuinely lose the news (a line over the 200-character
    limit, 2026-09-30; a malformed job id, 2026-10-04). Bucketing on the code would
    trade this defect for its mirror image, and the mirror image is the one that
    matters: a real hole rendered as fine.

    So `fleetnudge` records it as a field, and this reads the field. Reported by
    coord, who read the classifier rather than the symptom.
    """
    def test_the_field_decides(self):
        self.assertFalse(self.w.lost_the_news(
            {"outcome": "not delivered", "notified_otherwise": True}))
        self.assertTrue(self.w.lost_the_news(
            {"outcome": "not delivered", "notified_otherwise": False}))

    def test_an_absent_field_with_an_unknown_reason_is_a_hole(self):
        """The direction that keeps a real one visible. A record this cannot
        interpret is not a record saying everything is fine."""
        self.assertTrue(self.w.lost_the_news({"outcome": "not delivered"}))
        self.assertTrue(self.w.lost_the_news(
            {"outcome": "not delivered", "reason": "TEXT is 229 characters"}))

    def test_a_record_predating_the_field_is_read_from_its_reason(self):
        """LEGACY, and it is a parse of prose -- said here as plainly as in the
        code. It exists because records written before 2026-10-15 carry only the
        sentence, and `NUDGE_DAYS` is 7, so it becomes dead on 2026-10-22."""
        self.assertFalse(self.w.lost_the_news(
            {"outcome": "not delivered", "reason": self.w.INFORMED_LEGACY}))

    def test_the_legacy_sentence_is_the_one_fleetnudge_writes(self):
        """The guard that makes a prose match defensible rather than a guess.

        Matching a sentence another program emits is a dependency with nothing
        holding it together, and this repository keeps finding that family: two
        derivations of one fact, agreeing for a reason nobody wrote down. If the
        refusal is reworded, this fails here instead of silently turning two benign
        rows back into delivery holes.
        """
        import ast
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetnudge")).read()
        # Parsed, not grepped: the sentence is split across two source lines, and
        # a regex that reassembles it is a second guess about the thing being
        # pinned. ast gives the value the program actually builds.
        emitted = [t.elts[1].value for t in ast.walk(ast.parse(src))
                   if isinstance(t, ast.Tuple) and len(t.elts) == 2
                   and isinstance(t.elts[0], ast.Constant) and t.elts[0].value == "informed"
                   and isinstance(t.elts[1], ast.Constant)]
        self.assertEqual(len(emitted), 1,
                         "expected exactly one `informed` refusal in fleetnudge")
        self.assertEqual(emitted[0], self.w.INFORMED_LEGACY,
                         "fleetnudge's wording moved; update INFORMED_LEGACY or drop it")


class InformedRowsLeaveTheHoleReport(Delivery):
    """The bucketing, end to end, because `lost_the_news` being right is not the
    same as it being called."""
    def test_an_informed_row_is_in_neither_bucket(self):
        self.write(self.rec(outcome="not delivered", reason="in-session",
                            notified_otherwise=True, push="push sent (HTTP 200)"),
                   self.rec(job="222222", outcome="not delivered", reason="pane busy",
                            notified_otherwise=False, push="push sent (HTTP 200)"))
        h = self.w.nudge_holes()
        rows = h["silent"] + h["pushed"]
        self.assertEqual([r["job"] for r in rows], ["222222"],
                         "an informed decline was reported as a delivery hole")

    def test_an_informed_row_is_not_counted_as_an_older_one_either(self):
        """The same lie, one line up: `older` is the count a reader uses to decide
        whether the quiet window is quiet."""
        self.write(self.rec(ago_h=24 * 30, outcome="not delivered",
                            reason="in-session", notified_otherwise=True),
                   self.rec(ago_h=24 * 30, job="222222", outcome="not delivered",
                            reason="pane busy", notified_otherwise=False))
        self.assertEqual(self.w.nudge_holes()["older"], 1)

    def test_a_code_2_caller_error_is_still_a_hole(self):
        self.write(self.rec(outcome="not delivered", code=2,
                            reason="TEXT is 229 characters; the limit is 200",
                            notified_otherwise=False))
        h = self.w.nudge_holes()
        self.assertEqual(len(h["silent"] + h["pushed"]), 1)


class Clients(Base):
    """Who is attached to the tmux server -- the question the fleet's owner asked on
    2026-09-23: someone who logs in as him and runs `tmux a -d` has every pane.

    This REPORTS; it does not guard. Whoever can attach can equally read the
    Claude credentials, the gh token and the ssh key from the same account
    without tmux, so authenticating this one door would defend nothing.
    """
    LISTED = ("/dev/pts/0\tcfa\t1790163444\t1790178714\n"
              "/dev/pts/9\tcfa\t1790170000\t1790170001\n")
    WHO = ("u      pts/0        2026-09-23 07:37 (198.51.100.23)\n"
           "u      seat0        2026-09-18 10:16\n"
           "u      tty3         2026-09-18 10:16\n")

    def test_origin_comes_from_who_and_the_tty_names_are_reconciled(self):
        # tmux says /dev/pts/0; who says pts/0
        cs = self.w.parse_clients(self.LISTED, self.WHO)
        self.assertEqual([c["tty"] for c in cs], ["/dev/pts/0", "/dev/pts/9"])
        self.assertEqual(cs[0]["origin"], "198.51.100.23")
        self.assertEqual(cs[0]["created"], 1790163444)
        # a client `who` says nothing about is unknown, never assumed local
        self.assertEqual(cs[1]["origin"], "unknown")

    def test_a_local_console_login_is_not_a_remote_host(self):
        cs = self.w.parse_clients("/dev/seat0\tcfa\t1\t2\n", self.WHO)
        self.assertEqual(cs[0]["origin"], "local console")

    def test_blank_and_short_lines_are_skipped(self):
        self.assertEqual(self.w.parse_clients("\n\nbroken\n", self.WHO), [])

    def test_a_failed_query_is_an_error_not_an_empty_list(self):
        """The whole point: no rows must never be produced by the check failing.
        An unattached server and a broken tmux look identical from here."""
        class R:
            returncode, stdout, stderr = 1, "", "no server running on /tmp/x"
        with mock.patch.object(self.w.subprocess, "run", return_value=R()):
            cs, err = self.w.clients()
        self.assertEqual(cs, [])
        self.assertIsNotNone(err)
        self.assertIn("no server", err)

        with mock.patch.object(self.w.subprocess, "run", side_effect=OSError("tmux gone")):
            cs, err = self.w.clients()
        self.assertEqual((cs, "tmux gone"), ([], "tmux gone"))

    def out(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.w.print_clients(*a)
        return buf.getvalue()

    def test_an_error_never_prints_as_nobody_attached(self):
        text = self.out([], "boom")
        self.assertIn("NOT", text)
        self.assertNotIn("no tmux client attached", text)

    def test_one_client_is_quiet_and_two_are_not(self):
        one = self.out(self.w.parse_clients("/dev/pts/0\tcfa\t1790163444\t1790178714\n",
                                            self.WHO), None)
        self.assertNotIn("!!", one)
        self.assertIn("198.51.100.23", one)

        two = self.out(self.w.parse_clients(self.LISTED, self.WHO), None)
        self.assertIn("!! MORE THAN ONE CLIENT", two)
        self.assertIn("rotate", two)          # says what to do, not just that it happened

    def test_times_are_labelled_with_a_zone(self):
        """An unlabelled time in the wrong zone reads as right."""
        self.assertRegex(self.w._stamp_epoch(1790163444),
                         r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+$")
        self.assertEqual(self.w._stamp_epoch(None), "?")


class Arguments(Base):
    """`fleetwatch list` -- an invented subcommand -- was taken as a session
    filter, matched nothing, and printed "no live cluster work" with exit 0 while
    a live 8-task array was running. Reported 2026-09-25 after that line was
    quoted as this tool's verdict.

    The failure this tool exists to catch, committed by the tool itself for the
    second time. A false all-clear is worse than an error: nobody investigates a
    reassurance.
    """
    def parse(self, *argv, known=("alpha", "beta", "alpha-runs")):
        return self.w.parse_args(list(argv), set(known))

    def refused(self, *argv):
        with self.assertRaises(SystemExit) as e:
            self.parse(*argv)
        self.assertEqual(e.exception.code, 2)
        return e.exception

    def test_an_invented_subcommand_is_refused_not_answered(self):
        self.refused("list")
        self.refused("status")
        self.refused("--json", "list")      # refused even on the machine-readable path

    def test_a_known_session_still_filters(self):
        self.assertEqual(self.parse("alpha"), ("alpha", False))
        self.assertEqual(self.parse("alpha", "--json"), ("alpha", True))
        self.assertEqual(self.parse("--json", "alpha"), ("alpha", True))

    def test_no_arguments_is_the_whole_fleet(self):
        self.assertEqual(self.parse(), (None, False))
        self.assertEqual(self.parse("--json"), (None, True))

    def test_an_unknown_option_is_refused(self):
        self.refused("--jsonn")             # a typo used to be ignored silently
        self.refused("-x")

    def test_a_second_session_is_refused_rather_than_ignored(self):
        self.refused("alpha", "beta")

    def test_help_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e:
                self.parse("--help")
        self.assertEqual(e.exception.code, 0)

    def test_the_refusal_says_what_is_known(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                self.parse("list")
        text = err.getvalue()
        self.assertIn("alpha", text)        # so a typo is recoverable from the message
        self.assertIn("no arguments", text)

    def test_known_sessions_comes_from_colors_owners_and_registrations(self):
        d = os.path.join(self.cfg.state, "watchers")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "w.json"), "w") as f:
            json.dump({"session": "watcher-only", "job": "111111", "pid": 1}, f)
        known = self.w.known_sessions()
        self.assertIn("alpha", known)            # [colors]
        self.assertIn("beta", known)             # [colors]
        self.assertIn("alpha-runs", known)       # [owners]
        self.assertIn("watcher-only", known)     # a registration, with no other trace
        self.assertNotIn("UNATTRIBUTED", known)  # never a filterable name


if __name__ == "__main__":
    unittest.main()


class HowLongTheClusterHasBeenDown(Base):
    """The line that was missing. "CLUSTER QUERY FAILED" is honest and carries no
    duration, so a blip and a maintenance window read identically -- and so does a
    cluster nobody ever reached. The cluster was down on the morning of 2026-10-22 and
    nothing in the fleet could say when it had started."""

    def test_a_duration_is_coarse_on_purpose(self):
        """Nobody acts on the seconds of a two-day outage, and a bare count of
        them has to be divided by the reader."""
        self.assertEqual(self.w.duration(45), "45s")
        self.assertEqual(self.w.duration(600), "10m")
        self.assertEqual(self.w.duration(4800), "1h 20m")
        self.assertEqual(self.w.duration(200000), "2d 7h")

    def test_never_recorded_says_so_rather_than_giving_a_duration(self):
        """Absence is not zero: a state directory created a moment ago has not
        observed a cluster that has been down for no time at all."""
        line = self.w.down_line(None, {"last_good": None})
        self.assertIn("no successful query", line)
        self.assertNotIn("unreachable for", line)

    def test_a_recorded_outage_names_its_length_and_its_last_good_read(self):
        import time as _t
        last = _t.time() - 4800
        line = self.w.down_line(4800.0, {"last_good": last})
        self.assertIn("unreachable for 1h 20m", line)
        self.assertIn("last good", line)

    def test_the_absolute_time_carries_a_zone(self):
        """An unlabelled time in the wrong zone reads as right -- the rule this
        repository applies to every timestamp a person reads."""
        import re as _re, time as _t
        line = self.w.down_line(600.0, {"last_good": _t.time() - 600})
        self.assertTrue(_re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+$", line),
                        "expected a trailing zone label, got %r" % line)


class TheReservationTableRidesTheSameRoundTrip(Base):
    """coord proposed one ssh call on a schedule that already exists; folding it
    into the call already being made is cheaper, and it cannot add a failure mode
    -- it sits before the `--END--` marker, so a cluster that cannot run
    `scontrol` still produces the marker that says the query worked."""

    def jobs(self, out):
        with mock.patch.object(self.w, "sh", return_value=out):
            return self.w.live_jobs()

    def test_the_table_comes_back_with_the_jobs(self):
        out = ("23225789|RUNNING|None|2\n--WD--\n23225789|/w\n"
               "--RES--\nReservationName=maint Flags=MAINT\n--END--\n")
        jobs, ok, res = self.jobs(out)
        self.assertTrue(ok)
        self.assertIn("23225789", jobs)
        self.assertIn("Flags=MAINT", res)

    def test_reservation_lines_are_not_mistaken_for_jobs(self):
        """The row parser splits on `|`, and reservation output contains them."""
        out = ("--WD--\n--RES--\nReservationName=a|b|c|d\n--END--\n")
        jobs, ok, res = self.jobs(out)
        self.assertTrue(ok)
        self.assertEqual(jobs, {})
        self.assertIn("a|b|c|d", res)

    def test_a_cluster_without_scontrol_still_reports_its_jobs(self):
        out = ("23225789|RUNNING|None|2\n--WD--\n23225789|/w\n"
               "--RES--\nbash: scontrol: command not found\n--END--\n")
        jobs, ok, res = self.jobs(out)
        self.assertTrue(ok, "a scontrol failure must not read as a failed query")
        self.assertIn("23225789", jobs)
        self.assertIn("command not found", res)

    def test_a_failed_ssh_yields_no_reservation_text(self):
        """An empty string is not an observation that the table was empty."""
        jobs, ok, res = self.jobs("Welcome to the cluster\n")
        self.assertFalse(ok)
        self.assertEqual(res, "")


# The empty shape `nudge_holes` returns, named once. Spelled out rather than
# `{}` because `main` indexes it, and a short dict fails with a KeyError that
# looks like a bug in the tool rather than in the fixture.
NO_HOLES = {"silent": [], "pushed": [], "dangling": [], "older": 0, "resolved": 0,
            "bad_lines": 0, "unreadable": None, "days": 7, "mail_stuck": 0,
            "mail_error": None, "log": "/dev/null"}


class TheOutageLineReachesTheReport(Base):
    """`down_line` being right is not the same as it being PRINTED.

    Breaking the call in the failure branch left this suite green on
    2026-10-22: every test exercised the function directly and none drove the
    report that is supposed to carry it. Same shape as a membership rule imported
    by one tool and nothing else -- a correct answer nowhere anybody reads it.
    """

    def report(self, out, seeded_last_good=None):
        import io, contextlib
        if seeded_last_good is not None:
            self.w.reach.record(self.w.REACHFILE, self.w.CLUSTER_NAME, True,
                                now=seeded_last_good)
        buf = io.StringIO()
        with mock.patch.object(self.w, "sh", return_value=out), \
             mock.patch.object(self.w, "known_sessions", return_value=set()), \
             mock.patch.object(self.w, "watchers", return_value={}), \
             mock.patch.object(self.w, "registered", return_value=({}, [], {})), \
             mock.patch.object(self.w, "final_states", return_value={}), \
             mock.patch.object(self.w, "nudge_holes", return_value=NO_HOLES), \
             mock.patch.object(self.w, "clients", return_value=([], None)), \
             mock.patch.object(self.w.sys, "argv", ["fleetwatch"]), \
             contextlib.redirect_stdout(buf):
            try:
                self.w.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def test_a_failed_query_prints_the_duration(self):
        import time as _t
        out = self.report("Welcome to the cluster\n", seeded_last_good=_t.time() - 4800)
        self.assertIn("CLUSTER QUERY FAILED", out)
        self.assertIn("unreachable for 1h 20m", out)

    def test_a_failed_query_with_no_history_says_there_is_no_duration(self):
        out = self.report("Welcome to the cluster\n")
        self.assertIn("CLUSTER QUERY FAILED", out)
        self.assertIn("no successful query", out)

    def test_a_working_query_prints_no_outage_line(self):
        out = self.report("--WD--\n--RES--\nNo reservations in the system\n--END--\n")
        self.assertNotIn("CLUSTER QUERY FAILED", out)
        self.assertNotIn("unreachable for", out)

    def test_the_reservation_table_is_recorded_only_when_readable(self):
        self.report("--WD--\n--RES--\nNo reservations in the system\n--END--\n")
        self.assertIn("No reservations",
                      open(self.w.RESFILE).read())
        before = open(self.w.RESFILE).read()
        self.report("Welcome to the cluster\n")     # failed query, no output
        self.assertEqual(open(self.w.RESFILE).read(), before,
                         "a failed ssh is not an observation of an empty table")

    def test_a_truncated_response_does_not_record_a_partial_table(self):
        """The case the `cluster_ok` guard is actually for. An ssh that dies after
        the reservation lines but before `--END--` yields real text AND a failed
        query -- so the emptiness check in `fleet.reach` does not catch it, and
        without this guard a half-read table would be recorded as what the
        cluster said. Found by breaking the guard and watching nothing fail."""
        self.report("--WD--\n--RES--\nNo reservations in the system\n--END--\n")
        before = open(self.w.RESFILE).read()
        self.report("--WD--\n--RES--\nReservationName=half Flags=MAI")   # cut off
        self.assertEqual(open(self.w.RESFILE).read(), before,
                         "a truncated read is not an observation")
