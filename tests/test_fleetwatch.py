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
        jobs, ok = self.jobs(SQUEUE_OK)
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
        jobs, ok = self.jobs("Welcome to the cluster\n")
        self.assertEqual(jobs, {})
        self.assertFalse(ok)

    def test_empty_queue_is_ok(self):
        self.assertEqual(self.jobs("--WD--\n--END--\n"), ({}, True))

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
        live, dead = self.w.registered()
        self.assertEqual(live, {"alpha": {"111111"}})
        self.assertEqual(sorted(r["session"] for r in dead), ["beta", "gamma"])


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


class Clients(Base):
    """Who is attached to the tmux server -- the question Cameron asked on
    2026-09-23: someone who logs in as him and runs `tmux a -d` has every pane.

    This REPORTS; it does not guard. Whoever can attach can equally read the
    Claude credentials, the gh token and the ssh key from the same account
    without tmux, so authenticating this one door would defend nothing.
    """
    LISTED = ("/dev/pts/0\tcfa\t1790163444\t1790178714\n"
              "/dev/pts/9\tcfa\t1790170000\t1790170001\n")
    WHO = ("cfa      pts/0        2026-09-23 07:37 (10.246.157.49)\n"
           "cfa      seat0        2026-09-18 10:16\n"
           "cfa      tty3         2026-09-18 10:16\n")

    def test_origin_comes_from_who_and_the_tty_names_are_reconciled(self):
        # tmux says /dev/pts/0; who says pts/0
        cs = self.w.parse_clients(self.LISTED, self.WHO)
        self.assertEqual([c["tty"] for c in cs], ["/dev/pts/0", "/dev/pts/9"])
        self.assertEqual(cs[0]["origin"], "10.246.157.49")
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
        self.assertIn("10.246.157.49", one)

        two = self.out(self.w.parse_clients(self.LISTED, self.WHO), None)
        self.assertIn("!! MORE THAN ONE CLIENT", two)
        self.assertIn("rotate", two)          # says what to do, not just that it happened

    def test_times_are_labelled_with_a_zone(self):
        """An unlabelled time in the wrong zone reads as right."""
        self.assertRegex(self.w._stamp_epoch(1790163444),
                         r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+$")
        self.assertEqual(self.w._stamp_epoch(None), "?")


if __name__ == "__main__":
    unittest.main()
