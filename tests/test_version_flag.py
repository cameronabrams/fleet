"""Every tool answers `--version`, and the next one will have to as well.

There was no way to ask a running fleet which version it was, which stopped being
merely untidy once there were tags to point at. The awkward part was never the
flag: five tools parse `sys.argv` by hand, nine use argparse, two are shell, and
`fleetwatch` refuses an argument it does not recognise — so a flag added per tool
would have been four different shapes and one new refusal to remember.

This test is deliberately exhaustive rather than a sample. A per-tool test would
pass forever while a new tool quietly shipped without it.
"""
import os, re, subprocess, sys, unittest

from tests.support import APP, FakeConfig

import fleet

TOOLS = sorted(
    [os.path.join(APP, "bin", f) for f in os.listdir(os.path.join(APP, "bin"))
     if not f.startswith(".") and not f.endswith(".pyc")]
    + [os.path.join(APP, "install")])


class EveryToolReportsIt(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()

    def tearDown(self):
        self.cfg.close()

    def ask(self, tool, flag="--version"):
        return subprocess.run([tool, flag], capture_output=True, text=True,
                              timeout=60, env=dict(os.environ), cwd=APP)

    def test_there_are_tools_to_check(self):
        """Guard the guard: an empty list would make every test below vacuous."""
        self.assertGreaterEqual(len(TOOLS), 14, TOOLS)

    def test_every_tool_answers_and_exits_zero(self):
        wrong = []
        for tool in TOOLS:
            name = os.path.basename(tool)
            r = self.ask(tool)
            want = "%s (fleet %s)" % (name, fleet.__version__)
            if r.returncode != 0 or r.stdout.strip() != want:
                wrong.append("%s -> exit %s, %r" % (name, r.returncode, r.stdout.strip()))
        self.assertEqual(wrong, [], "these did not answer --version:\n  " +
                                    "\n  ".join(wrong))

    def test_the_short_form_works_too(self):
        r = self.ask(os.path.join(APP, "bin", "fleetwatch"), "-V")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(fleet.__version__, r.stdout)

    def test_it_is_answered_before_the_argument_refusal(self):
        """`fleetwatch` exits 2 on an argument it does not recognise. The version
        has to be answered before that, or the one tool with a strict parser would
        be the one that could not report itself."""
        r = self.ask(os.path.join(APP, "bin", "fleetwatch"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_tool_still_runs_normally_without_the_flag(self):
        """The flag returns immediately when it is absent; nothing else moved."""
        r = subprocess.run([os.path.join(APP, "bin", "fleetwatch"), "nosuchsession"],
                           capture_output=True, text=True, timeout=120,
                           env=dict(os.environ), cwd=APP)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("is not a session this fleet knows", r.stderr)

    def test_the_version_is_the_one_place_it_is_written(self):
        r = self.ask(os.path.join(APP, "bin", "fleetsnap"))
        self.assertIn(fleet.__version__, r.stdout)
        self.assertRegex(r.stdout.strip(), r"^fleetsnap \(fleet \d+\.\d+\.\d+\)$")


if __name__ == "__main__":
    unittest.main()
