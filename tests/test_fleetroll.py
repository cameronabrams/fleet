"""Rolling one named session, and every way it must refuse.

The tool exists for two reasons. The keystroke sequence was runbook prose an
agent could misread, and did: a coordinator read a resumed pane's REPLAYED
`/exit` farewells as five live failed exits and held every roll for nine
consecutive fires on a healthy session (2026-10-23). And under auto mode the
rule that would let an agent type at all, `Bash(tmux send-keys:*)`, is a prefix
rule that cannot constrain which keys reach which pane; a tool is what makes the
grant narrow.

So the refusals ARE the feature, and most of this file is about them.
"""
import io
import json
import os
import contextlib
import tempfile
import unittest
from unittest import mock

from tests.support import BASE_TOML, FakeConfig, load_tool

UUID = "aaaaaaaa-0000-4000-8000-000000000001"
IDLE = "❯ \n──────\n  ⏵⏵ auto mode on (shift+tab to cycle) · ← 1 agent\n"
BUSY = "· Working… (48s)\n❯ \n──────\n  ⏵⏵ auto mode on · esc to interrupt\n"
TRUST = "Is this a project you created or one you trust?\n"
TYPED = "❯ /exit\n──────\n  /exit  Exit the REPL\n"
# A resumed pane replays every `/exit` the session has ever made. Here the keys
# did NOT land: the live input line holds something else.
REPLAYED = ("❯ /exit\n  ⎿  Catch you later!\n❯ /exit\n  ⎿  Bye!\n"
            "──────\n❯ half-typed\n──────\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML + '\nalpha = "red"\n'
                              if "[colors]" not in BASE_TOML else BASE_TOML)
        self.store = tempfile.mkdtemp(dir=self.cfg.root)
        os.makedirs(os.path.join(self.store, "2.1.304"), exist_ok=True)
        open(os.path.join(self.store, "2.1.304"), "a").close() if False else None
        self.r = load_tool("fleetroll")
        self.screen = IDLE
        self.calls = []
        self.alive_pids = {4242}
        self.version_of = {4242: "2.1.302", 5555: "2.1.304"}
        self.agents = [{"name": "alpha"}]
        self.elig = {
            "asking": None, "installed": "2.1.308", "target": "2.1.304",
            "eligible": ["alpha"],
            "sessions": [{"name": "alpha", "version": "2.1.302",
                          "eligible": True, "why_not": []}],
        }
        self.pane_rows = "%7\t999\talpha\ttestfleet\n"
        self.next_pid = 5555
        self.anc = []                 # pids between us and the target, for self-roll

    def tearDown(self):
        self.cfg.close()

    def tmux(self, *a):
        self.calls.append(a)
        if a[0] == "list-panes":
            return 0, self.pane_rows, ""
        if a[0] == "capture-pane":
            return 0, self.screen, ""
        if a[0] == "send-keys" and a[-1] == "/exit":
            self.screen = TYPED
        if a[0] == "send-keys" and a[-1] == "Enter":
            self.alive_pids.discard(4242)
        if a[0] == "send-keys" and "--resume" in str(a):
            self.alive_pids.add(self.next_pid)
        return 0, "", ""

    def run_tool(self, *argv):
        """Short waits unless a test sets its own. The polls are real `time.sleep`
        calls, and at the production defaults (90s/180s) this file took over a
        minute -- a suite slow enough to skip is a suite that gets skipped."""
        if "--exit-wait" not in argv:
            argv = argv + ("--exit-wait", "2")
        if "--back-wait" not in argv:
            argv = argv + ("--back-wait", "4")
        r = self.r
        r.TYPE_WAIT = 1.0      # real polls; the production 10s is not under test here
        pid_now = [4242]

        def find_pane(name):
            if name != "alpha":
                return None, None, None, "no pane in this fleet carries @agent=%s" % name
            live = pid_now[0] if pid_now[0] in self.alive_pids else self.next_pid
            return "%7", live, "9", None

        buf = io.StringIO()
        with mock.patch.object(r, "tmux", side_effect=self.tmux), \
             mock.patch.object(r, "eligibility", side_effect=lambda: self.elig), \
             mock.patch.object(r, "find_pane", side_effect=find_pane), \
             mock.patch.object(r, "resume_uuid", side_effect=lambda p: UUID), \
             mock.patch.object(r, "versioned",
                               side_effect=lambda t: "/vers/%s" % t if t == "2.1.304" else None), \
             mock.patch.object(r, "ancestors", side_effect=lambda p: self.anc), \
             mock.patch.object(r, "alive",
                               side_effect=lambda p, s=None: p in self.alive_pids), \
             mock.patch.object(r, "list_agents", side_effect=lambda: self.agents), \
             mock.patch.object(r.versions, "of_pid",
                               side_effect=lambda p: self.version_of.get(int(p))), \
             mock.patch.object(r.sys, "argv", ["fleetroll"] + list(argv)), \
             contextlib.redirect_stdout(buf):
            try:
                code = r.main()
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()


class ItRefuses(Base):
    def test_an_unreadable_eligibility_is_not_eligible(self):
        """THE one that must never fail open. A roll that proceeded because the
        gate could not be consulted is a roll with no gate, and this tool calls
        `fleetupgrade` out precisely so there is one definition of eligible."""
        self.elig = None
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("UNKNOWN", out)
        self.assertNotIn("typed /exit", out)

    def test_it_quotes_fleetupgrades_reason_rather_than_keeping_its_own(self):
        self.elig["eligible"] = []
        self.elig["sessions"][0] = {"name": "alpha", "version": "2.1.302",
                                    "eligible": False, "why_not": ["status is busy"]}
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("status is busy", out)

    def test_a_session_cannot_roll_itself(self):
        """Typing /exit into our own pane kills the process mid-roll, and nothing
        is left to relaunch it. Tested on PID ancestry, not on the name: a name
        can be changed, process ancestry cannot."""
        self.anc = [4242]
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("cannot roll itself", out)

    def test_an_unknown_name_is_refused_not_guessed(self):
        code, out = self.run_tool("nobody", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("no pane", out)

    def test_already_on_target(self):
        self.elig["sessions"][0]["version"] = "2.1.304"
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("already on", out)

    def test_a_busy_pane_is_refused(self):
        self.screen = BUSY
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertNotIn("typed /exit", out)

    def test_a_dialog_is_refused_and_never_answered(self):
        """A trust prompt means a human has been asked something. Typing past one
        answers it on their behalf."""
        self.screen = TRUST
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertNotIn(("send-keys", "-t", "%7", "Enter"), self.calls)

    def test_no_target_and_no_override(self):
        self.elig["target"] = None
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("no target", out)

    def test_a_target_with_no_binary_in_the_store(self):
        code, out = self.run_tool("alpha", "--to", "9.9.9", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("no binary", out)


class ItReadsOnlyTheInputLine(Base):
    """The misread this tool was written after. A resumed pane replays every
    `/exit` it has ever made, so a screen-wide search for `❯ /exit` matches
    before a keystroke has landed."""

    def test_replayed_farewells_are_not_proof_the_keys_landed(self):
        def tmux(*a):
            r = Base.tmux(self, *a)
            if a[0] == "send-keys" and a[-1] == "/exit":
                self.screen = REPLAYED
            return r
        with mock.patch.object(self.r, "tmux", side_effect=tmux):
            self.tmux = tmux
            code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertNotIn(("send-keys", "-t", "%7", "Enter"), self.calls,
                         "Enter must not follow a /exit that never landed")


class TheSequence(Base):
    def test_a_plan_changes_nothing(self):
        code, out = self.run_tool("alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("plan only", out)
        self.assertFalse([c for c in self.calls if c[0] == "send-keys"])

    def test_a_roll_that_works(self):
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("rolled to 2.1.304", out)

    def test_it_relaunches_from_the_versioned_path_never_bare_claude(self):
        """A bare `claude` resolves to the NEWEST installed and defeats the soak
        gate the target came from."""
        self.run_tool("alpha", "--go")
        launches = [c for c in self.calls
                    if c[0] == "send-keys" and "--resume" in " ".join(map(str, c))]
        self.assertTrue(launches, "nothing was relaunched")
        line = " ".join(map(str, launches[0]))
        self.assertIn("/vers/2.1.304", line)
        self.assertNotRegex(line, r"(?<![/\w])claude --name")

    def test_a_session_that_will_not_exit_is_never_killed(self):
        """It is holding something, and killing it is how the thing it was
        holding becomes invisible."""
        def tmux(*a):
            r = Base.tmux(self, *a)
            if a[0] == "send-keys" and a[-1] == "Enter":
                self.alive_pids.add(4242)          # refuses to die
            return r
        with mock.patch.object(self.r, "tmux", side_effect=tmux):
            self.tmux = tmux
            code, out = self.run_tool("alpha", "--go", "--exit-wait", "1")
        self.assertEqual(code, 3, out)
        self.assertIn("NOT killed", out)
        self.assertFalse([c for c in self.calls if c[0] == "kill-pane"])

    def test_coming_back_on_the_wrong_version_is_its_own_exit_code(self):
        """Not merely advanced, and not equal to `installed`: equal to TARGET."""
        self.version_of[5555] = "2.1.308"
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 5, out)
        self.assertIn("came back on 2.1.308", out)

    def test_not_coming_back_at_all_is_exit_4(self):
        self.agents = []
        code, out = self.run_tool("alpha", "--go", "--back-wait", "1")
        self.assertEqual(code, 4, out)

    def test_the_color_is_reapplied_because_a_roll_drops_it(self):
        """`fleetupgrade` documents this: a `/color` record does not survive a
        roll, so a correctly named session comes back colorless."""
        code, out = self.run_tool("alpha", "--go")
        self.assertEqual(code, 0, out)
        self.assertTrue(any("/color" in " ".join(map(str, c)) for c in self.calls),
                        "the color was not re-applied")
