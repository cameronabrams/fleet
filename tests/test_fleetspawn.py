import os, tempfile, unittest
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
    actually up, correct and labelled -- confirmed by `--check` seconds later.
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
                return 0, "%16\talpha\talpha\tcoord", ""
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
        self.assertEqual(self.spawn.launch_cmd(a, "brief.md"), f"claude --name alpha --resume {UP}")

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
