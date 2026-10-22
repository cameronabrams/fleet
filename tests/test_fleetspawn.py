import io, os, tempfile, unittest
from types import SimpleNamespace
from unittest import mock
from tests.support import FakeConfig, load_tool

# Captured 2026-09-13 from claude 2.1.270 launched in an untrusted directory, on a
# private tmux server (`tmux -L`), never answered and killed by pid.
TRUST_SCREEN = """\
────────────────────────────────────────────────────────────────────────
 Accessing workspace:

 /home/u/.cache/probe

 Quick safety check: Is this a project you created or one you trust? (Like your own code, a well-known open source
 project, or work from your team). If not, take a moment to review what's in this folder first.

 Claude Code'll be able to read, edit, and execute files here.

 Security guide

 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
"""

LIVE_SCREEN = """\
 ▐▛███▛█   Claude Code v2.1.270
▝▜██████▀  Opus 5 (1M context)
─────────────────────────────── alpha ─
❯ Try "how do I log an error?"
"""

# A session that is up and working, with the startup banner no longer on screen.
# This is what EVERY running pane looks like a moment after launch: checked
# 2026-10-07 across 21 live panes, none of which held "Claude Code v". The banner
# is drawn once and scrolls off as soon as anything is printed over it.
RESUMED_SCREEN = """\
  ⎿  Read 42 lines

● The change is in place and the tests pass.

────────────────────────────── alpha ─
❯ 
"""


class ReadinessOutlivesTheBanner(unittest.TestCase):
    """`wait_for` gated readiness on the version banner being ON SCREEN.

    The banner is drawn once at startup and scrolls away as soon as the session
    prints anything. So the signal is destroyed by the very thing it is waiting
    for, and a session that comes up and gets to work FASTER is more likely to be
    reported as never having come up. A fresh spawn usually wins that race because
    it sits idle while its first prompt is read; a `--resume` always loses it,
    because replaying the conversation fills the pane immediately.

    Reported 2026-10-07: five `--resume` unparks in one day, plus two the day
    before, every one reported `TIMED OUT: no live claude named X` and every one
    actually up, correct and labeled -- confirmed by `--check` seconds later.
    **180s failed where 60s had succeeded**, which is the tell that it was never
    about duration: a marker that is gone cannot arrive by waiting.

    The reported cause was `[spawn].first_prompt` firing on a resume, leaving the
    session mid-turn. That is not it: `launch_cmd` returns early for `--resume` and
    sends no prompt. The symptom pointed the right way and the mechanism did not.

    A failure that fires on success is the dangerous direction here, because the
    natural responses -- relaunch, or retire and retry -- are the damaging ones.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.dir = tempfile.mkdtemp(dir=self.cfg.root)

    def tearDown(self):
        self.cfg.close()

    def wait(self, screen, procs, agents, timeout=1):
        with mock.patch.object(self.spawn, "tmux",
                               lambda *a: (0, screen, "")), \
             mock.patch.object(self.spawn, "claude_procs", lambda: procs), \
             mock.patch.object(self.spawn, "running_agents", lambda: agents):
            return self.spawn.wait_for("%9", "alpha", self.dir, timeout)

    def procs(self):
        return [(4242, self.dir, ["claude", "--name", "alpha", "--resume", "u"])]

    def test_a_working_session_without_the_banner_is_live(self):
        state, pid = self.wait(RESUMED_SCREEN, self.procs(),
                               {"alpha": self.dir})
        self.assertEqual(state, "live")
        self.assertEqual(pid, 4242)

    def test_the_banner_alone_is_still_sufficient(self):
        """The old evidence is still evidence. If `claude agents` cannot be read,
        a pane showing the banner must still pass -- otherwise the fix trades one
        unreachable readiness state for another."""
        state, pid = self.wait(LIVE_SCREEN, self.procs(), None)
        self.assertEqual(state, "live")
        self.assertEqual(pid, 4242)

    def test_the_trust_prompt_still_wins_over_both(self):
        """A process exists before the trust prompt renders, and the session is
        listed by nothing. Screen-only states are why the screen is read at all."""
        state, _ = self.wait(TRUST_SCREEN, self.procs(), {"alpha": self.dir})
        self.assertEqual(state, "trust")

    def test_a_process_of_that_name_in_another_directory_is_not_this_one(self):
        """`claude agents` is fleet-wide and answers only "is a session of this
        name up". The DIRECTORY is the process check's job.

        This test first asserted that against the agents mapping instead, and
        passed whether or not that check existed -- the process list it used was
        empty, so the process loop rejected the case on its own. A redundant
        condition is invisible to a test that cannot make the two disagree, which
        is the only reason the redundancy was noticed.
        """
        elsewhere = [(4242, "/somewhere/else",
                      ["claude", "--name", "alpha", "--resume", "u"])]
        state, _ = self.wait(RESUMED_SCREEN, elsewhere, {"alpha": self.dir},
                             timeout=1)
        self.assertEqual(state, "timeout")

    def test_nothing_running_still_times_out(self):
        state, _ = self.wait(RESUMED_SCREEN, [], {}, timeout=1)
        self.assertEqual(state, "timeout")


class Check(unittest.TestCase):
    """`fleetspawn --check` on a session whose process exists but is stuck at the
    folder-trust prompt. The process with --name in the right cwd exists BEFORE
    trust is granted, so a process check alone passes it (coord, 2026-09-13)."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.dir = tempfile.mkdtemp(dir=self.cfg.root)
        self.spawn = load_tool("fleetspawn")

    def tearDown(self):
        self.cfg.close()

    def run_check(self, screen):
        procs = [(4242, self.dir, ["claude", "--name", "alpha", "prompt"])]
        def tmux(*a):
            if a[0] == "list-panes":
                # tab-separated: pane, @agent, @repo, @fleet
                return 0, "%16\talpha\talpha\ttestfleet", ""
            if a[0] == "capture-pane":
                return 0, screen, ""
            return 1, "", "unexpected"
        names = getattr(self, "names", {})
        with mock.patch.object(self.spawn, "claude_procs", return_value=procs), \
             mock.patch.object(self.spawn, "tmux", side_effect=tmux), \
             mock.patch.object(self.spawn, "session_name",
                               side_effect=lambda p, c, v: (names.get(p, "alpha"), None, "")), \
             mock.patch("builtins.print"):
            return self.spawn.check(SimpleNamespace(name="alpha", dir=self.dir))

    def test_trust_prompt_is_not_live(self):
        self.assertEqual(self.run_check(TRUST_SCREEN), 3)

    def test_live_session_passes(self):
        self.assertEqual(self.run_check(LIVE_SCREEN), 0)

    def test_session_renamed_away_is_not_running_under_its_launch_name(self):
        self.names = {4242: "renamed"}
        self.assertEqual(self.run_check(LIVE_SCREEN), 1)

    def test_screen_state(self):
        self.assertEqual(self.spawn.screen_state(TRUST_SCREEN), "trust")
        self.assertEqual(self.spawn.screen_state(LIVE_SCREEN), "banner")
        self.assertEqual(self.spawn.screen_state("$ claude --name alpha"), "unknown")

    def test_named(self):
        self.assertTrue(self.spawn.named(["claude", "--name", "alpha"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "--name", "alphabet"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "alpha"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "--name"], "alpha"))


UP = "aaaaaaaa-0000-4000-8000-000000000001"

class Resume(unittest.TestCase):
    """Bringing a parked session back, and refusing retired ones."""
    toml_extra = (f'\n[parked.alpha]\nuuid = "{UP}"\nsince = "2026-09-13"\n'
                  '\n[retired.beta]\nuuid = "bbbbbbbb-0000-4000-8000-000000000002"\nsince = "2026-09-01"\n')

    def setUp(self):
        from tests.support import BASE_TOML
        self.cfg = FakeConfig(toml=BASE_TOML + self.toml_extra, briefs=("alpha", "beta"))
        self.dir = tempfile.mkdtemp(dir=self.cfg.root)
        self.spawn = load_tool("fleetspawn")

    def tearDown(self):
        self.cfg.close()

    def problems(self, name, resume=None):
        a = SimpleNamespace(name=name, dir=self.dir, beside=None, resume=resume)
        with mock.patch.object(self.spawn, "claude_procs", return_value=[]), \
             mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "session_name", return_value=(None, None, "")):
            return self.spawn.preflight(a, os.path.join(self.cfg.config, "briefs", f"{name}.md"))

    def test_parked_needs_its_own_resume_uuid(self):
        self.assertTrue(any("parked" in p for p in self.problems("alpha")))
        self.assertTrue(any("not cccccccc-" in p for p in
                            self.problems("alpha", "cccccccc-0000-4000-8000-000000000003")))
        self.assertEqual(self.problems("alpha", UP), [])

    def test_retired_is_refused_even_with_resume(self):
        self.assertTrue(any("retired" in p for p in self.problems("beta")))
        self.assertTrue(any("retired" in p for p in
                            self.problems("beta", "bbbbbbbb-0000-4000-8000-000000000002")))

    def test_another_sessions_transcript_is_refused(self):
        # alpha's color is declared; resuming beta's retired transcript under it is not allowed
        self.assertTrue(any("belongs to [retired.beta]" in p for p in
                            self.problems("alpha", "bbbbbbbb-0000-4000-8000-000000000002")))

    def test_a_renamed_session_already_answering_to_the_name_blocks(self):
        a = SimpleNamespace(name="gamma", dir=self.dir, beside=None, resume=None)
        procs = [(777, self.dir, ["claude", "--name", "gamma-old"])]
        with mock.patch.object(self.spawn, "claude_procs", return_value=procs), \
             mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "session_name", return_value=("gamma", None, "")):
            problems = self.spawn.preflight(a, os.path.join(self.cfg.config, "briefs", "alpha.md"))
        self.assertTrue(any("already running" in p for p in problems), problems)

    def test_resume_launch_has_no_first_prompt(self):
        a = SimpleNamespace(name="alpha", resume=UP)
        # Says which binary it expects. Without the patch this reads the HOST's
        # version store, so it passed on CI -- which has no claude installed --
        # and failed on any machine that has one.
        with mock.patch.object(self.spawn.versions, "target",
                               lambda *a, **k: (None, None)):
            self.assertEqual(self.spawn.launch_cmd(a, "brief.md"),
                             f"claude --name alpha --resume {UP}")

    def test_a_resume_launch_pins_the_target_when_there_is_one(self):
        """The other half, which no test asserted: with a soaked release the
        resume launch names it. Both directions, because the fallback passing is
        what hid the pin for a day."""
        a = SimpleNamespace(name="alpha", resume=UP)
        with mock.patch.object(self.spawn.versions, "target",
                               lambda *a, **k: ("2.1.303", "/v/2.1.303")), \
             mock.patch.object(self.spawn.os.path, "exists", lambda p: True):
            cmd = self.spawn.launch_cmd(a, "brief.md")
        self.assertIn("/v/2.1.303", cmd)
        self.assertNotIn("claude --name", cmd)
        self.assertIn("--resume %s" % UP, cmd)

    def test_resume_mode_prompt_is_the_humans(self):
        self.assertEqual(self.spawn.screen_state(
            "This session is 5h 35m old\n  1. Resume from summary (recommended)\n"), "resume")

if __name__ == "__main__":
    unittest.main()


RULE_ = "─" * 30
_D, _R = "\x1b[2m", "\x1b[0m"

def screen(line, footer="  footer"):
    """A pane as `capture-pane -p -e` renders it, around one input line."""
    return f"⏺ done\n{RULE_}\n{line}\n{RULE_}\n{footer}\n"

IDLE = screen("\x1b[39m❯\xa0")
BUSY = screen("\x1b[39m❯\xa0", footer="  esc to interrupt")
DRAFT = screen("\x1b[38;5;246m❯\xa0\x1b[39mhalf a thought")


class TheColorIsAppliedNotPrinted(unittest.TestCase):
    """fleetspawn required a declared color, refused to spawn without one, and
    then left it to be typed by hand -- so the color was declared, validated, and
    applied only if someone remembered. A session that misses it looks like
    somebody else's window on every board that reads the label.

    The old comment gave a real reason not to type it: keys sent into a session
    still working its first prompt arrive corrupted or land as prompt text
    (observed 2026-09-07). That hazard has since been solved elsewhere in this
    repo rather than avoided -- `panes.type_line` waits for an idle pane, refuses
    a dialog or a draft, and confirms the input line reads back exactly the
    intended text before Enter. This uses that path.

    Taken from `pkgyasi/fleet`, which made the argument and wrote it first.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.typed = []

    def tearDown(self):
        self.cfg.close()

    def run_apply(self, screens, color_now=None, color_after="blue", uuid="u-1"):
        """`screens` is what capture-pane returns on successive calls."""
        it = iter(screens)
        last = [screens[-1]]

        def tmux(*a):
            if a[0] == "capture-pane":
                try:
                    last[0] = next(it)
                except StopIteration:
                    pass
                return 0, last[0], ""
            self.typed.append(a)
            return 0, "", ""

        seen = {"n": 0}

        def agent_color(u):
            seen["n"] += 1
            return color_now if seen["n"] == 1 else color_after

        # The clock is driven, not slept through: the waits here are 5s and 3s of
        # wall time and the tests must not spend them. `sleep` alone is not enough
        # -- with it stubbed the loops spin on a real clock for the full duration,
        # which is how this first ran for 34 seconds.
        clock = iter(range(0, 10_000))
        with mock.patch.object(self.spawn, "tmux", tmux), \
             mock.patch.object(self.spawn, "session_uuid", lambda pid: uuid), \
             mock.patch.object(self.spawn, "agent_color", agent_color), \
             mock.patch.object(self.spawn.panes, "type_line",
                               lambda t, p, line, **k: self.typed.append(("TYPE", line))), \
             mock.patch.object(self.spawn.time, "sleep", lambda s: None), \
             mock.patch.object(self.spawn.time, "time", lambda: next(clock)):
            return self.spawn.apply_color("%1", "alpha", 42, "blue", 5, confirm_wait=3)

    def test_it_types_the_color_and_confirms_from_the_transcript(self):
        self.assertIsNone(self.run_apply([IDLE]))
        self.assertIn(("TYPE", "/color blue"), self.typed)
        self.assertIn(("send-keys", "-t", "%1", "C-m"), self.typed)

    def test_a_session_already_carrying_it_is_not_typed_into(self):
        """A resumed session carries its color forward. Typing into it would be a
        keystroke into a live session for no reason."""
        self.assertIsNone(self.run_apply([IDLE], color_now="blue"))
        self.assertEqual(self.typed, [])

    def test_a_busy_pane_is_waited_for_not_typed_into(self):
        problem = self.run_apply([BUSY, BUSY, IDLE])
        self.assertIsNone(problem, problem)
        self.assertIn(("TYPE", "/color blue"), self.typed)

    def test_a_pane_that_never_goes_idle_is_reported_not_typed_into(self):
        problem = self.run_apply([BUSY])
        self.assertIsNotNone(problem)
        self.assertNotIn(("TYPE", "/color blue"), self.typed)

    def test_a_draft_in_the_input_line_is_never_typed_over(self):
        problem = self.run_apply([DRAFT])
        self.assertIn("draft", problem)
        self.assertEqual(self.typed, [])

    def test_the_trust_prompt_stops_the_wait_at_once(self):
        """Waiting cannot clear it, and this tool never answers it."""
        problem = self.run_apply([TRUST_SCREEN])
        self.assertIn("trust", problem)
        self.assertEqual(self.typed, [])

    def test_sending_keys_is_not_the_success_test(self):
        """The guard the whole thing turns on. Keys always go out; the evidence is
        the session's own agent-color record. With the record never changing, this
        must report a failure even though every keystroke 'succeeded'."""
        problem = self.run_apply([IDLE], color_after=None)
        self.assertIsNotNone(problem, "a check that cannot fail is not evidence")
        self.assertIn("typed it", problem)
        self.assertIn(("TYPE", "/color blue"), self.typed)


class AColorThatWillNotApplyDoesNotFailTheSpawn(unittest.TestCase):
    """The session is up, in the right directory, with the right brief. Only its
    label is wrong. Exiting non-zero would invite the one response that makes it
    worse -- a retry, which respawns a session that is already live."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")

    def tearDown(self):
        self.cfg.close()

    def test_the_failure_is_printed_with_the_line_to_type(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetspawn")).read()
        tail = src[src.index("COLOR NOT APPLIED"):]
        self.assertIn("type  /color", tail)
        self.assertNotIn("sys.exit", tail,
                         "a color that did not apply must not fail the spawn")


class TheRegistryIsTheHandleForAQuietSession(unittest.TestCase):
    """`uuid_from_descendants` needs a live CHILD process, which a session has
    only while it is mid-tool-call -- exactly what `apply_color` has just finished
    waiting for it NOT to be.

    Measured on 14 live sessions (2026-10-13): the registry answered for all 14,
    the descendant walk for 1, and that one was the only session doing work. So
    the fork's version of this would have reported "found no transcript to confirm
    it from" almost every time, having typed the color correctly.
    """
    def setUp(self):
        # FakeConfig first: `fleetspawn` reads the configuration at IMPORT, so a
        # class that loads the tool without one reads the real `~/.config/fleet`.
        # This class did, and passed here and nowhere else -- CI has no fleet
        # configuration, which is the point of the rule it broke.
        self.cfg = FakeConfig()
        self.addCleanup(self.cfg.close)
        self.spawn = load_tool("fleetspawn")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def entry(self, pid, body):
        import json
        with open(os.path.join(self.tmp.name, f"{pid}.json"), "w") as f:
            json.dump(body, f)

    def uuid(self, pid):
        from fleet import transcripts
        with mock.patch.object(transcripts, "SESSIONS", self.tmp.name):
            return transcripts.registry_uuid(pid)

    def test_a_session_records_its_own_transcript(self):
        self.entry(42, {"pid": 42, "sessionId": "abc-123"})
        self.assertEqual(self.uuid(42), "abc-123")

    def test_a_stale_entry_for_a_reused_pid_is_refused(self):
        """Pids come round again. A registry file left by a dead session whose
        number was reissued would otherwise hand back another session's
        transcript -- a restore that reopens the wrong conversation."""
        self.entry(42, {"pid": 7, "sessionId": "someone-else"})
        self.assertIsNone(self.uuid(42))

    def test_missing_corrupt_and_empty_are_all_none(self):
        self.assertIsNone(self.uuid(999))
        with open(os.path.join(self.tmp.name, "5.json"), "w") as f:
            f.write("{not json")
        self.assertIsNone(self.uuid(5))
        self.entry(6, {"pid": 6})
        self.assertIsNone(self.uuid(6))

    def test_the_descendant_walk_is_the_fallback_not_the_first_source(self):
        with mock.patch.object(self.spawn, "registry_uuid", lambda p: "from-registry"), \
             mock.patch.object(self.spawn, "uuid_from_descendants", lambda p: "from-walk"):
            self.assertEqual(self.spawn.session_uuid(42), "from-registry")
        with mock.patch.object(self.spawn, "registry_uuid", lambda p: None), \
             mock.patch.object(self.spawn, "uuid_from_descendants", lambda p: "from-walk"):
            self.assertEqual(self.spawn.session_uuid(42), "from-walk")


class AnUnparkIsAnAdoption(unittest.TestCase):
    """`fleetspawn` has no version argument and wants none -- a park and unpark is
    a human act with its own reasons, and making it wait on a soak would be the
    wrong trade. But it puts a session onto whatever `claude` resolves to, and
    until 2026-10-16 it did so invisibly: the fleet's whole version spread came
    from unparks, and the auto-roll log said `rolled=none skipped=15` in the
    minute before one happened.

    Recording it is the fix. Gating it is not proposed and is not done here.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")

    def tearDown(self):
        self.cfg.close()

    def test_the_adoption_declares_its_kind(self):
        """`kind=spawn` or `kind=unpark`, so no reader has to infer it from the
        note. A daily cap on the auto-roll reads this log, and counting a spawn
        would block the roll on any day a session was created -- which is how the
        field came to exist."""
        import inspect
        src = inspect.getsource(self.spawn.main)
        call = src[src.index("record_adoption"):]
        call = call[:call.index(")") + 1]
        self.assertIn("kind=", call, "the adoption must say what it was")
        self.assertIn("unpark", call)
        self.assertIn("spawn", call)

    def test_the_version_logged_is_read_from_the_running_process(self):
        """Not from `installed()`. Between composing the launch and the session
        coming up -- up to `--wait` seconds -- a human can have upgraded, and the
        question this log answers is which binary this session is on."""
        import inspect
        src = inspect.getsource(self.spawn.main)
        i = src.index("record_adoption")
        before = src[:i]
        self.assertIn("versions.of_pid(pid)", before,
                      "the adoption must log the version actually running")
        self.assertNotIn("versions.installed()", before)

    def test_an_unpark_and_a_fresh_spawn_are_told_apart(self):
        """Calls the function `main` calls. The first version of this re-evaluated
        the conditional itself inside the test helper -- so it asserted that
        `"parked" if resume else "new"` equals "parked" when resume is set, which
        is true of the test and says nothing about the tool. It passed with the
        distinction deleted from `main` entirely."""
        self.assertEqual(self.spawn.adoption_kind("uuid-1"), ("parked", "unpark"))
        self.assertEqual(self.spawn.adoption_kind(None), ("new", "spawn"))
        self.assertEqual(self.spawn.adoption_kind(""), ("new", "spawn"))

    def test_main_uses_that_function_rather_than_repeating_it(self):
        import inspect
        self.assertIn("adoption_kind(a.resume)", inspect.getsource(self.spawn.main))

    def test_a_failed_log_does_not_fail_the_spawn(self):
        """The session is up and correct. A retry would respawn a live session,
        which is a worse outcome than a missing log line -- so the failure is
        printed and the exit code is untouched."""
        import inspect
        src = inspect.getsource(self.spawn.main)
        tail = src[src.index("record_adoption"):]
        self.assertIn("adoption not logged", tail)
        self.assertNotIn("sys.exit", tail)

    def test_it_logs_on_go_only(self):
        """A plan changes nothing, including the log. The dry run returns before
        a pane is ever made, so the adoption line must sit after that return."""
        import inspect
        src = inspect.getsource(self.spawn.main)
        self.assertLess(src.index("plan only -- re-run with --go"),
                        src.index("record_adoption"))


class LaunchingTheSoakedTargetNotTheNewest(unittest.TestCase):
    """The fleet runs the newest release that has SOAKED, so a launch names that
    version instead of taking whatever the installer's symlink points at.

    Before 2026-10-17 an unpark was the fleet's main uncontrolled route onto a
    fresh binary; pinning brings it under the same policy as a roll. The cost is
    a new failure mode -- a named version can be absent where bare `claude`
    always resolves to something -- and the fallback is the important half.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cfg.close)

    def target(self, version, exists=True):
        path = os.path.join(self.tmp.name, version or "none")
        if exists and version:
            open(path, "w").close()
        return mock.patch.object(self.spawn.versions, "target",
                                 lambda *a, **k: (version, path if version else None))

    def test_it_names_the_soaked_version(self):
        with self.target("2.1.301"):
            cmd, why = self.spawn.claude_cmd()
        self.assertIn("2.1.301", cmd)
        self.assertIn("pinned", why)

    def test_a_pruned_target_falls_back_to_bare_claude_and_says_so(self):
        """A session that refuses to start because a pinned release is missing is
        a far worse outcome than one that starts on a fresh binary."""
        with self.target("2.1.301", exists=False):
            cmd, why = self.spawn.claude_cmd()
        self.assertEqual(cmd, "claude")
        self.assertIn("gone from the version store", why)
        self.assertIn("2.1.301", why)

    def test_nothing_soaked_falls_back_and_says_so(self):
        """A fresh machine, or an npm install with no version store at all."""
        with self.target(None):
            cmd, why = self.spawn.claude_cmd()
        self.assertEqual(cmd, "claude")
        self.assertIn("nothing has soaked", why)

    def test_the_launch_command_uses_it_for_a_resume_and_a_first_prompt(self):
        a = SimpleNamespace(name="alpha", resume="u-1")
        with self.target("2.1.301"):
            self.assertIn("2.1.301", self.spawn.launch_cmd(a, "/b.md"))
            self.assertIn("2.1.301",
                          self.spawn.launch_cmd(SimpleNamespace(name="alpha", resume=None),
                                                "/b.md"))

    def test_the_path_is_quoted(self):
        """It goes into a shell line typed at a pane."""
        with mock.patch.object(self.spawn.versions, "target",
                               lambda *a, **k: ("2.1.301", "/a dir/2.1.301")):
            with mock.patch.object(self.spawn.os.path, "exists", lambda p: True):
                cmd, _ = self.spawn.claude_cmd()
        self.assertIn("'/a dir/2.1.301'", cmd)


class ScaffoldingTheStepsBeforeASpawn(unittest.TestCase):
    """`fleetspawn` already named every missing piece in preflight and then
    refused instead of offering. These flags offer.

    The boundary that matters: scaffolding a FILE is a kindness, writing its
    CONTENT is the thing the refusal exists to force.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.addCleanup(self.cfg.close)

    def src(self):
        return open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bin", "fleetspawn")).read()

    def test_a_template_brief_stops_rather_than_spawning(self):
        """`[spawn].first_prompt` tells a session to read its brief and follow
        it, so a template brief is a session told its role is to fill itself in.
        That fails QUIETLY -- a session behaving plausibly and owning nothing in
        particular -- where a missing brief fails at preflight."""
        body = self.src()
        i = body.index("def do_brief_from_example")
        fn = body[i:body.index("\ndef ", i + 10)]
        self.assertIn("NOT SPAWNED", fn)
        self.assertIn("return 0", fn)
        # it is dispatched before anything launches, and exits
        main = body[body.index("def main("):]
        self.assertIn("sys.exit(do_brief_from_example(a, brief))", main)
        self.assertLess(main.index("do_brief_from_example"),
                        main.index("plan only -- re-run with --go"))

    def test_it_does_not_overwrite_a_brief_that_exists(self):
        body = self.src()
        i = body.index("def do_brief_from_example")
        self.assertIn("Not overwritten", body[i:i + 600])

    def test_the_color_is_checked_against_the_accepted_set(self):
        """A color `/color` will not accept is a declaration that can never be
        satisfied, and `fleetsnap` would flag the mismatch forever."""
        body = self.src()
        i = body.index("def declare_color")
        fn = body[i:body.index("\ndef ", i + 10)]
        self.assertIn("fc.COLORS", fn)

    def test_a_failed_declaration_stops_the_spawn(self):
        """Rather than launching into a preflight that is now certain to fail."""
        body = self.src()
        i = body.index("def declare_color")
        fn = body[i:body.index("\ndef ", i + 10)]
        self.assertIn("sys.exit", fn)

    def test_scaffolding_runs_before_preflight_judges(self):
        """So preflight judges what will exist rather than what did."""
        main = self.src()[self.src().index("def main("):]
        for flag in ("a.create_dir", "a.color"):
            self.assertLess(main.index(flag), main.index("problems = preflight("),
                            flag)

    def test_preflight_rereads_the_config_rather_than_the_import_time_copy(self):
        """`--color` may have just written it. The module-level CFG is the file
        as it was at import -- the staleness that had a watched board listing a
        session as parked 22 hours after it was unparked."""
        body = self.src()
        self.assertNotIn("fc.colors(CFG)", body,
                         "a color is read from the import-time configuration")
        self.assertIn("fc.colors(fc.load())", body)


class SomewhereOtherThanTheFleetToTryItOut(unittest.TestCase):
    """`fleetspawn` creates panes and launches sessions, and had no way to do
    that anywhere but the live fleet.

    `fleetrestore` has had `--socket` since it grew an end-to-end test, for
    exactly this reason. `fleetspawn` had not -- so exercising it by hand on
    2026-10-20 spawned two real sessions onto the default tmux server, where every
    other tool then counted them as members of a fleet they do not belong to:
    `fleetsnap` demanded a brief and a color for them, and the auto-roll would have
    offered to roll one.

    **A tool that changes the live system needs somewhere else to be tried.** The
    absence of that is what turned a careless test into a fleet with two strangers
    in it.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.addCleanup(self.cfg.close)

    def test_the_socket_reaches_every_tmux_call(self):
        """One place builds the argv, so a tool cannot talk to two servers in one
        run -- which would create the pane on one and label it on the other."""
        calls = []
        with mock.patch.object(self.spawn.subprocess, "run",
                               side_effect=lambda argv, **k: calls.append(argv) or
                               mock.Mock(returncode=0, stdout="", stderr="")):
            self.spawn.SOCKET = "probe-server"
            try:
                self.spawn.tmux("has-session")
                self.spawn.tmux("list-panes", "-a")
            finally:
                self.spawn.SOCKET = None
        self.assertTrue(calls)
        for argv in calls:
            self.assertEqual(argv[:3], ["tmux", "-L", "probe-server"], argv)

    def test_no_socket_means_the_default_server(self):
        calls = []
        with mock.patch.object(self.spawn.subprocess, "run",
                               side_effect=lambda argv, **k: calls.append(argv) or
                               mock.Mock(returncode=0, stdout="", stderr="")):
            self.spawn.SOCKET = None
            self.spawn.tmux("has-session")
        self.assertEqual(calls[0], ["tmux", "has-session"])

    def test_the_callers_server_is_never_inherited(self):
        """`$TMUX` is set inside any pane, so a run from a pane on another server
        would silently build there -- the same fault `fleetrestore` names."""
        seen = {}
        with mock.patch.object(self.spawn.subprocess, "run",
                               side_effect=lambda argv, **k: seen.update(k) or
                               mock.Mock(returncode=0, stdout="", stderr="")):
            self.spawn.tmux("has-session")
        self.assertNotIn("TMUX", seen.get("env", {}))

    def test_the_flag_is_wired_before_anything_is_built(self):
        import inspect
        main = inspect.getsource(self.spawn.main)
        self.assertIn("SOCKET = a.socket", main)
        self.assertLess(main.index("SOCKET = a.socket"), main.index("preflight("))


class APaneSaysWhichFleetItIsIn(unittest.TestCase):
    """Set at creation, because that is the only moment the spawning
    configuration is known for certain. A pane labeled later is labeled from a
    guess -- which is why `fleetinit --label-panes` refuses to touch a pane
    already carrying another fleet's name."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.addCleanup(self.cfg.close)

    def test_the_pane_is_given_the_fleets_name(self):
        import inspect
        main = inspect.getsource(self.spawn.main)
        self.assertIn('opts.append(("@fleet", ours))', main)
        self.assertIn("fc.fleet_name(fc.load())", main)
        # beside @agent, in the same loop, so a pane cannot get one without the other
        self.assertLess(main.index('("@agent", a.name)'),
                        main.index('tmux("set-option", "-p", "-t", pane, opt, val)'))
        self.assertLess(main.index('opts.append(("@fleet", ours))'),
                        main.index('tmux("set-option", "-p", "-t", pane, opt, val)'))

    def test_an_unnamed_fleet_says_so_rather_than_labeling_blank(self):
        """A blank `@fleet` would read as unlabeled anyway, so the useful thing
        is to tell the human their fleet cannot be told apart."""
        import inspect
        main = inspect.getsource(self.spawn.main)
        i = main.index("if not ours:")
        self.assertIn("no @fleet", main[i:i + 400])


class TheFirstSpawnOfANewFleet(unittest.TestCase):
    """`fleetinit` ships `[colors]` empty, so the very first spawn on a fresh
    machine always lands on the no-colour refusal -- and with `--color` given it
    did so three lines under its own "would declare alpha = 'blue'". A
    contradiction at that moment has nothing else on screen to be weighed
    against, and reads as the flag having been ignored.

    Walked end to end on 2026-10-21 on a throwaway HOME, which is how it was
    found; no test covered the fresh-machine path at all.
    """

    def setUp(self):
        self.cfg = FakeConfig()
        self.dir = tempfile.mkdtemp(dir=self.cfg.root)
        self.spawn = load_tool("fleetspawn")

    def tearDown(self):
        self.cfg.close()

    def preflight(self, color=None, brief=True):
        # Every attribute `preflight` reads, named rather than inherited from a
        # parser: a namespace missing one fails with AttributeError, which is a
        # different test failing for a different reason than the one it claims.
        a = SimpleNamespace(name="newbie", dir=self.dir, color=color,
                            resume=None, beside=None)
        path = os.path.join(self.cfg.config, "briefs", "newbie.md")
        if brief:
            with open(path, "w") as f:
                f.write("# brief\n")
        with mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "claude_procs", return_value=[]):
            return self.spawn.preflight(a, path)

    def test_an_undeclared_color_still_blocks(self):
        """A colour is how a human tells two panes apart at a glance, and a fleet
        that silently grows an undeclared session has lost that."""
        problems = self.preflight()
        self.assertTrue(any("no color declared" in p for p in problems))

    def test_the_refusal_names_the_flag_that_clears_it(self):
        problems = self.preflight()
        self.assertTrue(any("--color" in p for p in problems),
                        "the refusal must say how to satisfy it")

    def test_passing_color_clears_the_block(self):
        self.assertEqual(self.preflight(color="blue"), [])

    def test_a_declared_color_needs_no_flag(self):
        # Into the EXISTING [colors] table. Appending a second one is invalid
        # TOML -- "Cannot declare ('colors',) twice" -- and the test would then
        # fail on a parse error rather than on the behaviour it names.
        path = os.path.join(self.cfg.config, "fleet.toml")
        text = open(path).read().replace("[colors]\n", '[colors]\nnewbie = "green"\n', 1)
        with open(path, "w") as f:
            f.write(text)
        self.assertEqual(self.preflight(), [])

    def test_a_missing_brief_still_blocks_whatever_the_color(self):
        """`--color` clears its own blocker and nothing else."""
        problems = self.preflight(color="blue", brief=False)
        self.assertTrue(any("no brief" in p for p in problems))


class TheBriefIsWrittenNotFilledIn(unittest.TestCase):
    """Cameron, 2026-10-21: "I didn't say no briefs. I said no user copying and
    editing a brief md file. Every session needs one -- it is the session's
    identity -- its role, scope, etc. An agent should be smart enough to interpret
    user specs about role and scope interactively as needing to be recorded
    out-of-context in a brief."

    By the time anyone asks for a session they have already said what it is for.
    Writing that down is transcription, not authorship, and answering with
    `cp examples/brief.example.md` asks them to redo the part already done.

    Out-of-context on purpose: what was said interactively lives in a transcript,
    and transcripts compact. The brief is the copy that survives a restart, a
    `/clear` and a power cycle.
    """

    BRIEF = "# alpha -- repo session for the parser\n\n**Kind:** repo.\n"

    def setUp(self):
        self.cfg = FakeConfig(briefs=())
        self.dir = tempfile.mkdtemp(dir=self.cfg.root)
        self.spawn = load_tool("fleetspawn")
        self.brief = os.path.join(self.cfg.config, "briefs", "alpha.md")

    def tearDown(self):
        self.cfg.close()

    def run_write(self, text, go=True):
        a = SimpleNamespace(name="alpha", dir=self.dir, go=go, brief_stdin=True)
        with mock.patch.object(self.spawn.sys, "stdin", io.StringIO(text)), \
             mock.patch("builtins.print"):
            self.spawn.write_brief(a, self.brief)

    # -- the point ------------------------------------------------------------

    def test_the_brief_is_written_from_what_was_supplied(self):
        self.run_write(self.BRIEF)
        self.assertEqual(open(self.brief).read(), self.BRIEF)

    def test_a_trailing_newline_is_added_if_missing(self):
        self.run_write("# alpha -- the parser")
        self.assertTrue(open(self.brief).read().endswith("\n"))

    def test_nothing_is_written_without_go(self):
        self.run_write(self.BRIEF, go=False)
        self.assertFalse(os.path.exists(self.brief))

    def test_preflight_does_not_block_on_a_brief_this_run_will_write(self):
        """The `--color` contradiction again if it did: "would write 12 lines of
        brief" three rows above "BLOCKED: no brief"."""
        a = SimpleNamespace(name="alpha", dir=self.dir, color="red", resume=None,
                            beside=None, brief=None, brief_stdin=True)
        with mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "claude_procs", return_value=[]):
            problems = self.spawn.preflight(a, self.brief)
        self.assertEqual([p for p in problems if "brief" in p], [])

    def test_without_the_flag_a_missing_brief_still_blocks(self):
        a = SimpleNamespace(name="alpha", dir=self.dir, color="red", resume=None,
                            beside=None, brief=None, brief_stdin=False)
        with mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "claude_procs", return_value=[]):
            problems = self.spawn.preflight(a, self.brief)
        self.assertTrue(any("no brief" in p for p in problems))

    def test_the_refusal_names_the_flag_rather_than_a_template_to_copy(self):
        a = SimpleNamespace(name="alpha", dir=self.dir, color="red", resume=None,
                            beside=None, brief=None, brief_stdin=False)
        with mock.patch.object(self.spawn, "tmux", return_value=(0, "", "")), \
             mock.patch.object(self.spawn, "claude_procs", return_value=[]):
            problems = self.spawn.preflight(a, self.brief)
        said = " ".join(p for p in problems if "brief" in p)
        self.assertIn("--brief-stdin", said)

    # -- the three refusals, each quieter than itself if allowed --------------

    def test_an_empty_brief_is_refused(self):
        """A session whose brief says nothing is told its role is nothing, and
        `[spawn].first_prompt` still sends it there to look."""
        with self.assertRaises(SystemExit) as e:
            self.run_write("   \n\n  ")
        self.assertIn("nothing on stdin", str(e.exception))
        self.assertFalse(os.path.exists(self.brief))

    def test_the_shipped_example_verbatim_is_refused(self):
        """A session told that its role is to fill itself in: it behaves
        plausibly and owns nothing in particular, where a missing brief fails
        loudly at preflight."""
        with open(self.spawn.BRIEF_EXAMPLE) as f:
            example = f.read()
        with self.assertRaises(SystemExit) as e:
            self.run_write(example)
        self.assertIn("shipped example", str(e.exception))
        self.assertFalse(os.path.exists(self.brief))

    def test_an_existing_brief_is_never_overwritten(self):
        os.makedirs(os.path.dirname(self.brief), exist_ok=True)
        with open(self.brief, "w") as f:
            f.write("# the real one\n")
        with self.assertRaises(SystemExit) as e:
            self.run_write(self.BRIEF)
        self.assertIn("already exists", str(e.exception))
        self.assertEqual(open(self.brief).read(), "# the real one\n")

    def test_an_edited_example_is_accepted(self):
        """Only the UNCHANGED example is refused. Someone who started from it and
        made it theirs has done the thing being asked for."""
        with open(self.spawn.BRIEF_EXAMPLE) as f:
            text = f.read() + "\n**Territory:** ~/Git/alpha only.\n"
        self.run_write(text)
        self.assertIn("Territory", open(self.brief).read())
