import glob, json, os, subprocess, sys, unittest
from tests.support import APP, FakeConfig

TOOL = os.path.join(APP, "bin", "fleetregister")

class Register(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    def test_register_then_clear_only_after_exit(self):
        r = self.run_tool("alpha", "123456", self.proc.pid, "a note")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = glob.glob(self.watch + "/alpha-123456-*.json")
        self.assertEqual(len(files), 1)
        rec = json.load(open(files[0]))
        self.assertEqual((rec["session"], rec["job"], rec["pid"]), ("alpha", "123456", self.proc.pid))
        self.assertTrue(rec["starttime"].isdigit())

        r = self.run_tool("--clear", "alpha", "123456")
        # 3, not 1: 1 means "no registration matched", and a refusal used to be
        # reported the same way, so a caller could not tell nothing-to-do from
        # nothing-cleared. Nothing consumes this code programmatically -- every
        # reference in the tools is a command printed for a human to run.
        self.assertEqual(r.returncode, 3)
        self.assertIn("still alive", r.stderr)
        self.assertTrue(os.path.exists(files[0]))

        self.proc.kill(); self.proc.wait()
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(files[0]))

    def test_register_dead_pid_refused(self):
        self.proc.kill(); self.proc.wait()
        r = self.run_tool("alpha", "123456", self.proc.pid)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(glob.glob(self.watch + "/*.json"), [])

    def test_clear_nothing_registered(self):
        self.assertEqual(self.run_tool("--clear", "alpha", "999999").returncode, 1)

    def test_clear_with_reused_pid_clears(self):
        # registration names a live pid but a different starttime: the watcher is gone
        os.makedirs(self.watch, exist_ok=True)
        path = os.path.join(self.watch, f"alpha-123456-{self.proc.pid}.json")
        json.dump({"session": "alpha", "job": "123456", "pid": self.proc.pid,
                   "starttime": "1"}, open(path, "w"))
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(path))

class ClearWithALiveSibling(unittest.TestCase):
    """The re-armed case -- a dead old pid beside a live new one -- which is what
    every restart produces. `--clear` used to `exit 1` from INSIDE the loop on
    meeting the live registration, so every dead file sorting after it survived.

    The glob is lexical on the pid string, so whether a clear worked depended on
    which pid happened to sort first: it silently worked or silently no-opped.
    Found 2026-09-30 after four restarts in three days, with a stale entry
    visible in fleetwatch.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    # pid_max on Linux is at most 4194304, so this can never name a live process,
    # and it sorts after any real pid under the shell's collation (leading 9).
    DEAD_PID = "999999999"

    def glob_order(self):
        """The order the SHELL expands the glob in -- not Python's.

        The first version of this test built the dead file as "<livepid>0" and
        asserted it sorted later using Python's `>`, which compares bytes. The
        shell collates by locale, which largely ignores punctuation: it expanded
        "...142670.json" BEFORE "...14267.json", the opposite order. So the dead
        file was cleared before the live one was reached and the test passed with
        the bug reintroduced. An assertion in the wrong collation cannot fail."""
        r = subprocess.run(
            ["/bin/bash", "-c",
             'for f in "$1"/alpha-123456-*.json; do basename "$f"; done', "_", self.watch],
            capture_output=True, text=True)
        return r.stdout.split()

    def dead_file(self, pid):
        """A registration for a pid that is not running."""
        os.makedirs(self.watch, exist_ok=True)
        path = os.path.join(self.watch, "alpha-123456-%s.json" % pid)
        with open(path, "w") as f:
            json.dump({"session": "alpha", "job": "123456", "pid": int(pid),
                       "starttime": "1", "armed": "then", "note": ""}, f)
        return path

    def test_a_live_registration_does_not_abandon_the_rest(self):
        live = self.run_tool("alpha", "123456", self.proc.pid, "live")
        self.assertEqual(live.returncode, 0, live.stderr)
        # sorts after the live pid: same digits plus one, so lexically later
        dead = self.dead_file(self.DEAD_PID)
        order = self.glob_order()
        self.assertEqual(order[-1], os.path.basename(dead),
                         "the dead file must be LAST in the shell's own expansion "
                         "or this test cannot reproduce the bug: %r" % order)

        r = self.run_tool("--clear", "alpha", "123456")
        self.assertFalse(os.path.exists(dead), "the dead entry survived: " + r.stderr)
        self.assertTrue(glob.glob(self.watch + "/alpha-123456-%d.json" % self.proc.pid),
                        "the LIVE registration must be left alone")

    def test_a_partial_clear_is_not_reported_as_success(self):
        self.run_tool("alpha", "123456", self.proc.pid, "live")
        self.dead_file(self.DEAD_PID)
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("skipped 1 live", r.stderr)

    def test_skipping_everything_does_not_read_as_nothing_to_do(self):
        """With only a live entry, the old tail said "no registration for ...",
        which reads as nothing-to-do rather than nothing-cleared."""
        self.run_tool("alpha", "123456", self.proc.pid, "live")
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertNotIn("no registration", r.stderr)
        self.assertIn("cleared 0", r.stderr)

    def test_a_clean_clear_still_exits_zero(self):
        self.dead_file(self.DEAD_PID)
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()


class RefusingAWatcherThatIsMidSet(unittest.TestCase):
    """The refusal is right; the advice attached to it was not.

    One watcher may poll several jobs, which the registry models as several rows
    sharing a pid. When the first of them finishes, `fleetwatch` sends someone
    here with a clear command -- and the refusal said "stop the watcher first",
    which would forfeit the jobs still running. Reported 2026-10-06 from
    sweep-session, pid 645241 over three jobs with one completed.

    Behavior is unchanged: still refused, still exit 3. Only what it tells you
    to do is different, and only when this pid holds other registrations.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    def test_a_set_is_named_and_stopping_the_watcher_is_warned_against(self):
        for j in ("111111", "222222", "333333"):
            self.assertEqual(self.run_tool("sweep", j, self.proc.pid).returncode, 0)
        r = self.run_tool("--clear", "sweep", "333333")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("2 other job(s)", r.stderr)
        self.assertIn("clears itself when it exits", r.stderr)
        self.assertIn("Do NOT stop it", r.stderr)
        self.assertNotIn("stop the watcher first", r.stderr)
        self.assertTrue(glob.glob(self.watch + "/sweep-333333-*.json"),
                        "the registration must survive the refusal")

    def test_a_lone_watcher_still_gets_the_plain_advice(self):
        """With no set to forfeit, stopping the watcher IS the way to clear it.
        The new wording must not reach the case the old wording was right for."""
        self.assertEqual(self.run_tool("solo", "444444", self.proc.pid).returncode, 0)
        r = self.run_tool("--clear", "solo", "444444")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("stop the watcher first", r.stderr)
        self.assertNotIn("other job(s)", r.stderr)

    def test_another_session_sharing_the_pid_is_not_this_watcher_s_set(self):
        """The count is per session AND pid. A pid registered under a different
        session name is a different watcher as far as this tool can tell, and
        counting it would overstate what stopping the process costs."""
        self.assertEqual(self.run_tool("sweep", "111111", self.proc.pid).returncode, 0)
        self.assertEqual(self.run_tool("other", "222222", self.proc.pid).returncode, 0)
        r = self.run_tool("--clear", "sweep", "111111")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("stop the watcher first", r.stderr)


class DeclaringLocalWork(unittest.TestCase):
    """`--local`: the registered pid IS the work, not a poller of a SLURM job.

    Without it every registration read as cluster work, so `fleetwatch` asked
    squeue about a name that could not be in it and reported a healthy local
    process as a monitor whose job had died.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    def rec(self, pattern):
        files = glob.glob(os.path.join(self.watch, pattern))
        self.assertEqual(len(files), 1, files)
        return json.load(open(files[0]))

    def test_the_flag_is_recorded_and_the_file_is_still_json(self):
        r = self.run_tool("--local", "alpha", "crawl", self.proc.pid, "a note")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = self.rec("alpha-crawl-*.json")
        self.assertEqual(rec["work"], "local")
        self.assertEqual(rec["note"], "a note", "the note still lands after the flag")
        self.assertTrue(rec["starttime"].isdigit())

    def test_without_the_flag_nothing_is_declared(self):
        """Not `work: cluster`. A default declaration would turn the one mistake
        this flag exists for -- local work registered without it -- into a claim
        that the work IS on the cluster, which is worse than saying nothing: an
        undeclared record is still checked against `job_id_re` and reported as
        something nothing can speak for."""
        self.assertEqual(self.run_tool("beta", "123456", self.proc.pid).returncode, 0)
        self.assertNotIn("work", self.rec("beta-123456-*.json"))

    def test_a_local_registration_clears_like_any_other(self):
        self.run_tool("--local", "alpha", "crawl", self.proc.pid)
        self.assertEqual(self.run_tool("--clear", "alpha", "crawl").returncode, 3,
                         "refused while the pid is alive, flag or no flag")
        self.proc.kill(); self.proc.wait()
        self.assertEqual(self.run_tool("--clear", "alpha", "crawl").returncode, 0)
        self.assertEqual(glob.glob(os.path.join(self.watch, "alpha-crawl-*.json")), [])


class CalledWrongIsNotCalledEmpty(unittest.TestCase):
    """A usage error must not share an exit code with a benign no-op.

    `--clear` took its arguments with `${2:?session}` / `${3:?jobid}`, which
    writes to stderr and exits 1. A watcher's exit path wrote

        fleetregister --clear "$SESSION" 2>/dev/null

    -- the real arity is `--clear <session> <jobid>` -- so the redirect swallowed
    the only evidence and the status was 1, which is the documented "no
    registration matched". The caller could not tell "I called this wrong and
    nothing happened" from "there was nothing to clear", and the second reading
    is the comfortable one. It leaves behind exactly the dead registration the
    clear exists to remove, and that surfaces later as an alarm with nothing
    connecting it back. Reported 2026-10-27 after it happened.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    def test_a_short_clear_is_refused_not_reported_as_nothing_to_clear(self):
        r = self.run_tool("--clear", "alpha")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("usage", r.stderr.lower())

    def test_nothing_to_clear_keeps_its_own_code(self):
        """The other half: the two readings must stay apart in BOTH directions,
        or the fix has only moved which one is ambiguous."""
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_a_short_register_is_refused_too(self):
        """Same defect on the register path: `${3:?pid}` exited 1, which is also
        `pid not running -- nothing to register`."""
        for args in ((), ("alpha",), ("alpha", "123456")):
            with self.subTest(args=args):
                r = self.run_tool(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("usage", r.stderr.lower())

    def test_a_dead_pid_still_refuses_with_its_own_code(self):
        self.proc.kill(); self.proc.wait()
        r = self.run_tool("alpha", "123456", self.proc.pid)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("not running", r.stderr)

    def test_the_local_flag_does_not_shift_the_arity_check(self):
        r = self.run_tool("--local", "alpha", "crawl")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_a_trailing_argument_too_many_is_refused(self):
        """`--clear` ignored anything after the job id, so a note copied from the
        register call -- the obvious mistake -- was accepted in silence."""
        r = self.run_tool("--clear", "alpha", "123456", "a note")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_the_refusal_names_the_arity_it_wanted(self):
        """A usage error that does not say the usage sends the reader to the
        source. Both forms, because the one you called wrong is the one you need
        printed."""
        self.assertIn("--clear <session> <jobid>",
                      self.run_tool("--clear", "alpha").stderr)
        self.assertIn("<session> <jobid> <pid>", self.run_tool("alpha").stderr)
