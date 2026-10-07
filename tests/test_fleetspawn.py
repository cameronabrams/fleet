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
        # alpha's colour is declared; resuming beta's retired transcript under it is not allowed
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
