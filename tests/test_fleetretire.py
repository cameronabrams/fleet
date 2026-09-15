import contextlib, io, json, os, subprocess, sys, tempfile, unittest
from types import SimpleNamespace
from unittest import mock
from tests.support import BASE_TOML, FakeConfig, load_tool

UUID = "aaaaaaaa-0000-4000-8000-000000000001"
IDLE = "❯ \n──────\n  ⏵⏵ auto mode on (shift+tab to cycle) · ← 1 agent\n"
BUSY = "· Working… (48s)\n❯ \n──────\n  ⏵⏵ auto mode on (shift+tab to cycle) · esc to interrupt\n"
TYPED = "❯ /exit\n──────\n  /exit  Exit the REPL\n"


class Base(unittest.TestCase):
    toml = BASE_TOML

    def setUp(self):
        self.cfg = FakeConfig(toml=self.toml, briefs=("alpha", "beta"))
        self.r = load_tool("fleetretire")
        self.cwd = tempfile.mkdtemp(dir=self.cfg.root)          # not a git repo
        self.screen = IDLE
        self.alive = True
        self.calls = []
        self.procs = [(4242, self.cwd, ["claude", "--name", "alpha", "--resume", UUID])]
        self.pane = {"pane": "%7", "window": "@2", "panes": 2, "label": "alpha", "fleet": "f"}
        self.watch = ({"cluster_ok": True, "jobs": []}, "")
        self.kids = []
        self.handle = (UUID, "verified: --resume in process argv")
        self.current = {}                       # pid -> name after a /rename
        self.agents = []                        # `claude agents --json`; None = unreadable

    def tearDown(self):
        self.cfg.close()

    def tmux(self, *a):
        self.calls.append(a)
        if a[0] == "capture-pane":
            return 0, self.screen, ""
        if a[0] == "send-keys" and a[-1] == "/exit":
            self.screen = TYPED
        if a[0] == "send-keys" and a[-1] == "Enter":
            self.alive = False
        return 0, "", ""

    def patches(self):
        r = self.r
        return [mock.patch.object(r, "claude_procs", side_effect=lambda: self.procs),
                mock.patch.object(r, "tmux", side_effect=self.tmux),
                mock.patch.object(r, "pane_of", side_effect=lambda pid: self.pane),
                mock.patch.object(r, "children", side_effect=lambda pid: self.kids),
                mock.patch.object(r, "fleetwatch_json", side_effect=lambda n: self.watch),
                mock.patch.object(r, "starttime", return_value="123"),
                mock.patch.object(r, "alive", side_effect=lambda pid, st=None: self.alive),
                mock.patch.object(r, "session_name", side_effect=self.session_name),
                mock.patch.object(r, "list_agents", side_effect=lambda *a, **k: self.agents),
                mock.patch.object(r.time, "sleep")]

    def session_name(self, pid, cwd, argv):
        launched = next((argv[i + 1] for i, x in enumerate(argv[:-1]) if x == "--name"), None)
        return (self.current.get(pid, launched),) + self.handle

    def gather(self, mode="park", allow_dirty=False):
        a = SimpleNamespace(name="alpha", mode=mode, allow_dirty=allow_dirty,
                            allow_references=False)
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            return self.r.gather(a)

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            st.enter_context(mock.patch.object(sys, "argv", ["fleetretire", *argv]))
            st.enter_context(contextlib.redirect_stdout(out))
            try:
                self.r.main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def blocked(self, problems, text):
        self.assertTrue(any(text in p for p in problems), f"{text!r} not in {problems}")


class Preflight(Base):
    def test_clean_session_passes(self):
        f, problems, notes = self.gather()
        self.assertEqual(problems, [])
        self.assertEqual(f["uuid"], UUID)
        self.assertTrue(any("not a git work tree" in n for n in notes))

    def test_busy_blocks(self):
        self.screen = BUSY
        self.blocked(self.gather()[1], "mid-turn")

    def test_trust_prompt_blocks(self):
        self.screen = "Is this a project you created or one you trust?"
        self.blocked(self.gather()[1], "folder-trust")

    def test_not_running_blocks(self):
        self.procs = []
        self.blocked(self.gather()[1], "no claude process")

    def test_renamed_session_is_found_by_its_current_name(self):
        # launched --name alpha-old, then /rename alpha (observed 2026-09-15)
        self.procs = [(4242, self.cwd, ["claude", "--name", "alpha-old", "--resume", UUID])]
        self.current = {4242: "alpha"}
        f, problems, _ = self.gather()
        self.assertEqual(problems, [])
        self.assertEqual(f["pid"], 4242)

    def test_session_renamed_away_is_not_matched_by_its_launch_name(self):
        self.current = {4242: "something-else"}
        f, problems, notes = self.gather()
        self.blocked(problems, "no claude process")
        self.assertTrue(any("now named 'something-else'" in n for n in notes))

    def test_background_session_with_the_name_blocks(self):
        self.agents = [{"kind": "background", "name": "alpha", "sessionId": "b20bc72b-x", "state": "working"}]
        self.blocked(self.gather()[1], "BACKGROUND session already answers")

    def test_unreadable_agent_list_is_a_note_not_a_pass(self):
        self.agents = None
        f, problems, notes = self.gather()
        self.assertEqual(problems, [])
        self.assertTrue(any("background sessions not checked" in n for n in notes))

    def test_duplicate_name_blocks(self):
        self.procs = self.procs + [(4343, self.cwd, ["claude", "--name", "alpha"])]
        self.blocked(self.gather()[1], "2 processes")

    def test_unverified_uuid_blocks(self):
        self.handle = (UUID, "UNVERIFIED: guess")
        self.blocked(self.gather()[1], "not verified")

    def test_children_block(self):
        self.kids = [os.getpid()]
        self.blocked(self.gather()[1], "child processes")

    def test_live_registered_watcher_blocks_and_dead_one_is_a_note(self):
        d = os.path.join(self.cfg.state, "watchers"); os.makedirs(d)
        json.dump({"session": "alpha", "job": "111111", "pid": 1, "starttime": "9"},
                  open(os.path.join(d, "a.json"), "w"))
        self.blocked(self.gather()[1], "registered watcher on job 111111 is alive")
        self.alive = False
        f, problems, notes = self.gather()
        self.assertEqual(problems, [])
        self.assertTrue(any("fleetregister --clear alpha 111111" in n for n in notes))

    def test_failed_cluster_query_blocks(self):
        self.watch = ({"cluster_ok": False, "jobs": []}, "")
        self.blocked(self.gather()[1], "cluster query failed")
        self.watch = (None, "exit 1")
        self.blocked(self.gather()[1], "fleetwatch failed")

    def test_owned_jobs_block(self):
        self.watch = ({"cluster_ok": True, "jobs": [{"job": "222222", "held": True}]}, "")
        self.blocked(self.gather()[1], "222222 (held)")

    def git_repo(self, dirty):
        run = lambda *a: subprocess.run(["git", "-C", self.cwd, *a], capture_output=True, check=True)
        run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
        open(os.path.join(self.cwd, "f"), "w").write("x"); run("add", "f"); run("commit", "-qm", "c")
        if dirty:
            open(os.path.join(self.cwd, "g"), "w").write("y")

    def test_dirty_repo_blocks_unless_allowed(self):
        self.git_repo(dirty=True)
        self.blocked(self.gather()[1], "uncommitted")
        _, problems, notes = self.gather(allow_dirty=True)
        self.assertEqual(problems, [])
        self.assertTrue(any("(allowed)" in n for n in notes))

    def test_dirty_repo_shared_with_another_session_is_only_a_note(self):
        self.git_repo(dirty=True)
        self.procs = self.procs + [(5555, self.cwd, ["claude", "--name", "beta"])]
        f, problems, notes = self.gather()
        self.assertEqual(problems, [])
        self.assertTrue(any("shared with pid 5555" in n for n in notes))

    def test_clean_repo_passes(self):
        self.git_repo(dirty=False)
        self.assertEqual(self.gather()[1], [])

    def test_references_block_retire_not_park(self):
        open(os.path.join(self.cfg.config, "briefs", "beta.md"), "w").write("Works with `alpha`.\n")
        self.assertEqual(self.gather(mode="park")[1], [])
        self.blocked(self.gather(mode="retire")[1], "named in other briefs: beta")

    def test_reference_match_is_whole_word(self):
        open(os.path.join(self.cfg.config, "briefs", "beta.md"), "w").write("see alpha-runs and alphabet\n")
        self.assertEqual(self.gather(mode="retire")[1], [])

    def test_self_blocks(self):
        self.procs = [(os.getppid(), self.cwd, ["claude", "--name", "alpha", "--resume", UUID])]
        self.blocked(self.gather()[1], "cannot stop itself")


class Act(Base):
    def ledger(self, sub=""):
        return os.path.join(self.cfg.state, "rearm", sub, "alpha.md")

    def test_plan_changes_nothing(self):
        code, out = self.main("alpha", "--park")
        self.assertEqual(code, 0)
        self.assertIn("plan only", out)
        self.assertFalse(any(c[0] == "send-keys" for c in self.calls))
        self.assertFalse(os.path.exists(self.ledger()))

    def test_blocked_exits_2_and_stops_nothing(self):
        self.screen = BUSY
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 2)
        self.assertFalse(any(c[0] == "send-keys" for c in self.calls))

    def test_park_writes_recipe_before_exit_then_closes_pane(self):
        seen = {}
        orig = self.tmux
        pending = self.ledger() + ".pending"
        def tmux(*a):
            if a[0] == "send-keys" and "first_send" not in seen:
                seen["first_send"] = os.path.exists(pending) and UUID in open(pending).read()
                seen["ledger_untouched"] = open(self.ledger()).read() == "# old ledger\nre-arm nothing\n"
            return orig(*a)
        self.tmux = tmux
        os.makedirs(os.path.dirname(self.ledger()))
        open(self.ledger(), "w").write("# old ledger\nre-arm nothing\n")
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 0, out)
        self.assertTrue(seen["first_send"])                        # recipe existed before any key
        self.assertTrue(seen["ledger_untouched"])                  # ...but not yet as the ledger
        self.assertFalse(os.path.exists(pending))
        text = open(self.ledger()).read()
        self.assertIn(f"claude --name alpha --resume {UUID}", text)
        self.assertIn("# old ledger", text)                        # previous content kept
        self.assertIn(("kill-pane", "-t", "%7"), self.calls)
        self.assertIn("[parked.alpha]", out)
        self.assertIn(f'uuid  = "{UUID}"', out)
        self.assertIn('group = "f"', out)                         # keeps its chart lane
        self.assertIn(f'cwd   = "{self.cwd}"', out)

    def test_retire_moves_ledger(self):
        os.makedirs(os.path.dirname(self.ledger()))
        open(self.ledger(), "w").write("# old\n")
        code, out = self.main("alpha", "--retire", "--go")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.ledger()))
        self.assertIn("# old", open(self.ledger("retired")).read())
        self.assertIn("[retired.alpha]", out)

    def test_pane_alone_in_window_is_left_open(self):
        self.pane = dict(self.pane, panes=1)
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 0, out)
        self.assertFalse(any(c[0] == "kill-pane" for c in self.calls))
        self.assertIn("left open", out)

    def test_corrupted_input_line_is_cleared_and_not_entered(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            if a[0] == "send-keys" and a[-1] == "/exit":
                self.screen = "❯ 8;32;42;52c/exit\n"
            return r
        self.tmux = tmux
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 3, out)
        self.assertIn(("send-keys", "-t", "%7", "C-u"), self.calls)
        self.assertNotIn(("send-keys", "-t", "%7", "Enter"), self.calls)

    def test_background_dialog_stops_with_3(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            if a[0] == "send-keys" and a[-1] == "Enter":
                self.alive = True
                self.screen = "Background work is running\n  1. Exit and stop tasks\n"
            return r
        self.tmux = tmux
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 3, out)
        self.assertFalse(any(c[0] == "kill-pane" for c in self.calls))

    def moved(self, screen_after_enter=None, agents_after=None):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            if a[0] == "send-keys" and a[-1] == "Enter":
                if screen_after_enter:
                    self.screen = screen_after_enter
                if agents_after is not None:
                    self.agents = agents_after
            return r
        self.tmux = tmux
        os.makedirs(os.path.dirname(self.ledger()))
        open(self.ledger(), "w").write("# old ledger\n")
        return self.main("alpha", "--park", "--go")

    def test_exit_that_backgrounds_the_session_is_not_a_stop(self):
        # observed 2026-09-15 on 2.1.272
        code, out = self.moved(screen_after_enter="Moving to background…\nbackgrounded · b20bc72b\n"
                                                  "  claude attach b20bc72b    open in this terminal\n")
        self.assertEqual(code, 3, out)
        self.assertIn("claude attach b20bc72b", out)
        self.assertEqual(open(self.ledger()).read(), "# old ledger\n")        # not marked PARKED
        self.assertTrue(os.path.exists(self.ledger() + ".pending"))
        self.assertFalse(any(c[0] == "kill-pane" for c in self.calls))

    def test_background_marker_while_the_old_pid_lingers(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            if a[0] == "send-keys" and a[-1] == "Enter":
                self.alive = True                       # the old process has not exited yet
                self.screen = "backgrounded · b20bc72b\n"
            return r
        self.tmux = tmux
        code, out = self.main("alpha", "--park", "--go", "--wait", "30")
        self.assertEqual(code, 3, out)
        self.assertIn("MOVED alpha TO THE BACKGROUND", out)

    def test_pid_gone_but_a_background_session_answers_to_the_name(self):
        code, out = self.moved(agents_after=[{"kind": "background", "name": "alpha",
                                              "sessionId": "b20bc72b-0000-4000-8000-000000000000"}])
        self.assertEqual(code, 3, out)
        self.assertIn("NOT stopped", out)
        self.assertEqual(open(self.ledger()).read(), "# old ledger\n")

    def test_unreadable_agent_list_still_stops_but_says_so(self):
        self.agents = None
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("to confirm nothing moved to the background -- check ListAgents", out)

    def test_slow_echo_is_waited_for(self):
        orig = self.tmux
        state = {"captures": 0}
        def tmux(*a):
            if a[0] == "capture-pane" and self.screen == TYPED:
                state["captures"] += 1
                if state["captures"] < 4:
                    self.calls.append(a)
                    return 0, IDLE, ""                   # not echoed yet
            return orig(*a)
        self.tmux = tmux
        code, out = self.main("alpha", "--park", "--go")
        self.assertEqual(code, 0, out)

    def test_timeout_exits_4(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            self.alive = True
            return r
        self.tmux = tmux
        import itertools
        clock = itertools.count(0, 0.6)                      # every reading advances 0.6 s
        with mock.patch.object(self.r.time, "time", side_effect=lambda: next(clock)):
            code, out = self.main("alpha", "--park", "--go", "--wait", "1")
        self.assertEqual(code, 4, out)


class Recorded(Base):
    toml = BASE_TOML + f'\n[parked.alpha]\nuuid = "{UUID}"\nsince = "2026-09-13"\n'

    def test_parked_and_not_running_retire_prints_config_only(self):
        self.procs = []
        code, out = self.main("alpha", "--retire")
        self.assertEqual(code, 0, out)
        self.assertIn("[retired.alpha]", out)
        self.assertFalse(self.calls)

    def test_recorded_but_running_blocks(self):
        code, out = self.main("alpha", "--park")
        self.assertEqual(code, 2)
        self.assertIn("already [parked]", out)


if __name__ == "__main__":
    unittest.main()
