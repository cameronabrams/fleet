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
                return 0, "%16 alpha coord", ""
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


RULE = "─" * 20


class ApplyColor(unittest.TestCase):
    """`/color` typed into a newly spawned session.

    The hazard: keys sent while a session is still working its first prompt
    arrive corrupted or land as prompt text (2026-09-07). So the colour goes only
    into an idle pane, and "typed" is not accepted as "applied" -- send-keys
    always succeeds, so it cannot be the test.

    The fake pane echoes what is typed into its input line, which is what
    `panes.type_line` reads back before pressing Enter.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.spawn = load_tool("fleetspawn")
        self.states = ["idle"]      # one per capture; the last repeats
        self.held = ""              # what the input line shows
        self.sent = []

    def tearDown(self):
        self.cfg.close()

    def screen(self):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if state == "trust":
            return TRUST_SCREEN
        footer = "esc to interrupt" if state == "busy" else "footer"
        return f"⏺ ready\n{RULE}\n❯ {self.held}\n{RULE}\n  {footer}\n"

    def tmux(self, *a):
        if a[0] == "capture-pane":
            return 0, self.screen(), ""
        if a[0] == "send-keys":
            self.sent.append(a)
            if "-l" in a:
                self.held += a[-1]
            elif "-H" in a:
                self.held += bytes.fromhex(a[-1]).decode()
            else:                      # C-u, BSpace, C-m all leave it empty
                self.held = ""
        return 0, "", ""

    def run_apply(self, color_records, idle_wait=6, confirm_wait=2):
        """color_records: what agent_color returns, one per call (the last repeats)."""
        recs = list(color_records)
        def agent_color(_uuid):
            return recs.pop(0) if len(recs) > 1 else recs[0]
        with mock.patch.object(self.spawn, "tmux", side_effect=self.tmux), \
             mock.patch.object(self.spawn, "uuid_from_descendants", return_value="u-1"), \
             mock.patch.object(self.spawn, "agent_color", side_effect=agent_color), \
             mock.patch.object(self.spawn.time, "sleep"), \
             mock.patch.object(self.spawn.panes.time, "sleep"):
            return self.spawn.apply_color("%7", "alpha", 4242, "red",
                                          idle_wait, confirm_wait)

    def typed(self):
        return [a[-1] for a in self.sent if "-l" in a]

    def test_applied_when_the_transcript_records_it(self):
        self.assertIsNone(self.run_apply([None, "red"]))
        self.assertEqual(self.typed(), ["/color red"])
        self.assertIn(("send-keys", "-t", "%7", "C-m"), self.sent)

    def test_waits_for_a_busy_pane_rather_than_typing_into_it(self):
        self.states = ["busy", "busy", "idle"]
        self.assertIsNone(self.run_apply([None, "red"]))
        self.assertEqual(self.typed(), ["/color red"])

    def test_a_pane_that_never_goes_idle_is_reported_not_typed_into(self):
        self.states = ["busy"]
        problem = self.run_apply([None])
        self.assertIn("mid-turn", problem)
        self.assertEqual(self.typed(), [])

    def test_a_draft_in_the_input_line_is_never_appended_to(self):
        self.held = "half a sentence"
        problem = self.run_apply([None])
        self.assertIn("already holds text", problem)
        self.assertEqual(self.typed(), [])
        self.assertEqual(self.held, "half a sentence")

    def test_the_trust_prompt_is_not_waited_out(self):
        self.states = ["trust"]
        problem = self.run_apply([None])
        self.assertIn("folder-trust", problem)
        self.assertEqual(self.typed(), [])

    def test_typed_but_never_recorded_is_a_failure_not_a_success(self):
        """Without this, a colour that silently never applied reads as applied."""
        problem = self.run_apply([None])
        self.assertIsNotNone(problem)
        self.assertIn("still records", problem)

    def test_a_session_already_the_right_colour_is_not_typed_into(self):
        """A resumed session carries its colour forward; retyping would drop a
        stray line into a conversation that is already under way."""
        self.assertIsNone(self.run_apply(["red"]))
        self.assertEqual(self.sent, [])
