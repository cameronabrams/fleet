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
        with mock.patch.object(self.spawn, "claude_procs", return_value=procs), \
             mock.patch.object(self.spawn, "tmux", side_effect=tmux), \
             mock.patch("builtins.print"):
            return self.spawn.check(SimpleNamespace(name="alpha", dir=self.dir))

    def test_trust_prompt_is_not_live(self):
        self.assertEqual(self.run_check(TRUST_SCREEN), 3)

    def test_live_session_passes(self):
        self.assertEqual(self.run_check(LIVE_SCREEN), 0)

    def test_screen_state(self):
        self.assertEqual(self.spawn.screen_state(TRUST_SCREEN), "trust")
        self.assertEqual(self.spawn.screen_state(LIVE_SCREEN), "banner")
        self.assertEqual(self.spawn.screen_state("$ claude --name alpha"), "unknown")

    def test_named(self):
        self.assertTrue(self.spawn.named(["claude", "--name", "alpha"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "--name", "alphabet"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "alpha"], "alpha"))
        self.assertFalse(self.spawn.named(["claude", "--name"], "alpha"))

if __name__ == "__main__":
    unittest.main()
