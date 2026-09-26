import contextlib, io, itertools, json, os, subprocess, sys, tempfile, unittest
from unittest import mock
from tests.support import BASE_TOML, FakeConfig, load_tool

UUID = "aaaaaaaa-0000-4000-8000-000000000001"
NOW = 1_800_000_000
RULE = "─" * 40
# Screens as 2.1.272 draws them: the input line sits between two rules, and an
# empty one is the prompt followed by a no-break space.
IDLE = f"⏺ done\n{RULE}\n❯ \n{RULE}\n  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents\n"
BUSY = f"· Working… (48s)\n{RULE}\n❯ \n{RULE}\n  ⏵⏵ auto mode on · esc to interrupt\n"
DRAFT = f"⏺ done\n{RULE}\n❯ commit and push main.tex\n{RULE}\n  ⏵⏵ auto mode on\n"
HISTORY = f"❯ status report\n⏺ All clean.\n{RULE}\n❯ \n{RULE}\n  footer\n"

def typed(cmd):
    return f"⏺ done\n{RULE}\n❯ {cmd}\n{RULE}\n  /compact  Clear history but keep a summary\n"


class Base(unittest.TestCase):
    toml = BASE_TOML

    def setUp(self):
        self.cfg = FakeConfig(toml=self.toml, briefs=())
        self.brief("alpha", "Kind: repo\n")
        self.brief("beta", "Kind: production\n")
        self.c = load_tool("fleetcontext")
        self.cwd = tempfile.mkdtemp(dir=self.cfg.root)          # not a git repo
        self.screen = IDLE
        self.calls = []
        self.procs = [(4242, self.cwd, ["claude", "--name", "alpha", "--resume", UUID])]
        self.agents = [{"pid": 4242, "name": "alpha", "sessionId": UUID, "kind": "interactive",
                        "status": "idle"}]
        self.pane_pids = {4242: "%7"}
        self.unlabelled = []   # panes in another tmux session, with no @repo/@fleet
        self.kids = []
        self.clock = itertools.count(NOW, 1)
        self.stats = {"tokens": 300_000, "turns": 12, "compactions": 0, "since": NOW - 7200,
                      "mtime": NOW - 3600, "path": "x", "last_compact": None}
        self.boundaries = []
        self.color = None
        self.compacts_on_enter = True

    def tearDown(self):
        self.cfg.close()

    def brief(self, name, text):
        with open(os.path.join(self.cfg.config, "briefs", f"{name}.md"), "w") as f:
            f.write(text)

    def tmux(self, *a):
        self.calls.append(a)
        if a[0] == "capture-pane":
            return 0, self.screen, ""
        if a[0] == "send-keys" and "-l" in a:
            self.screen = typed(a[-1])
        elif a[0] == "send-keys" and a[-1] == "Enter":
            self.screen = IDLE
            if self.compacts_on_enter:
                self.boundaries.append({"pre": 300_000, "post": 9_000})
            self.color = "red"
        elif a[0] == "send-keys" and a[-1] == "C-u":
            self.screen = IDLE
        return 0, "", ""

    def patches(self):
        c = self.c
        return [mock.patch.object(c, "claude_procs", side_effect=lambda: self.procs),
                mock.patch.object(c, "list_agents", side_effect=lambda *a, **k: self.agents),
                mock.patch.object(c, "panes", side_effect=lambda: (self.pane_pids, self.unlabelled)),
                mock.patch.object(c, "tmux", side_effect=self.tmux),
                mock.patch.object(c, "children", side_effect=lambda pid: self.kids),
                mock.patch.object(c, "context_stats", side_effect=lambda u: self.stats),
                mock.patch.object(c, "compactions", side_effect=lambda u: list(self.boundaries)),
                mock.patch.object(c, "agent_color", side_effect=lambda u: self.color),
                mock.patch.object(c, "starttime", return_value="123"),
                mock.patch.object(c, "alive", return_value=True),
                mock.patch.object(c, "ppid", return_value=1),
                mock.patch.object(c, "SELF_UUID", "not-this-one"),
                mock.patch.object(c.time, "sleep"),
                # every reading advances the clock one second, so each wait loop ends
                mock.patch.object(c.time, "time", side_effect=lambda: next(self.clock))]

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.patches():
                st.enter_context(p)
            st.enter_context(mock.patch.object(sys, "argv", ["fleetcontext", *argv]))
            st.enter_context(contextlib.redirect_stdout(out))
            try:
                self.c.main()
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def replace_patch(self, attribute, patch):
        base = self.patches
        self.patches = lambda: [p for p in base() if p.attribute != attribute] + [patch]

    def typed_keys(self):
        return [c for c in self.calls if c[0] == "send-keys"]


class Screens(Base):
    def test_input_line(self):
        il = self.c.input_line
        self.assertEqual(il(IDLE), "")
        self.assertEqual(il(DRAFT), "commit and push main.tex")
        self.assertEqual(il(HISTORY), "")                       # an echoed prompt is history
        self.assertIsNone(il("no box drawn here\n"))
        wrapped = f"{RULE}\n❯ /compact keep job ids, file\n  paths and decisions\n{RULE}\n"
        self.assertEqual(il(wrapped), "/compact keep job ids, file paths and decisions")

    def test_screen_state(self):
        ss = self.c.screen_state
        self.assertEqual(ss(IDLE), "idle")
        self.assertEqual(ss(BUSY), "busy")
        self.assertEqual(ss(DRAFT), "input")
        self.assertEqual(ss("Is this a project you created or one you trust?"), "trust")
        self.assertEqual(ss("Background work is running\n  1. Exit"), "dialog")
        self.assertEqual(ss("just text"), "no-prompt")

    def test_brief_kind(self):
        self.brief("gamma", "You are `gamma`, a fleet session (kind: writing).\n")
        self.brief("delta", "Kind: coordinator.\n")
        self.brief("eps", "Kind: <repo | production>\n")
        self.assertEqual(self.c.brief_kind("gamma"), "writing")
        self.assertEqual(self.c.brief_kind("delta"), "coordinator")
        self.assertIsNone(self.c.brief_kind("eps"))
        self.assertIsNone(self.c.brief_kind("nobody"))


class Recommend(Base):
    def row(test, **kw):          # not `self`: a row has a "self" field
        r = {"tokens": 300_000, "verified": True, "uuid_source": "verified", "self": False,
             "kind": "repo", "background": False, "state": "idle", "idle_s": 3600,
             "dirty": 0, "runtime": []}
        r.update(kw)
        return r

    def rec(test, **kw):
        return test.c.recommend(test.row(**kw))[0]

    def test_rules(self):
        self.assertEqual(self.rec(tokens=249_999), "leave")
        self.assertEqual(self.rec(), "compact")
        self.assertEqual(self.rec(state="busy"), "later")
        self.assertEqual(self.rec(state="input"), "later")
        self.assertEqual(self.rec(idle_s=60), "later")
        self.assertEqual(self.rec(self=True), "manual")
        self.assertEqual(self.rec(kind="coordinator"), "manual")
        self.assertEqual(self.rec(background=True), "manual")
        self.assertEqual(self.rec(tokens=None, verified=False), "unknown")

    def test_clear_candidate_needs_kind_clean_tree_and_no_runtime(self):
        self.assertEqual(self.rec(tokens=600_000), "clear?")
        self.assertEqual(self.rec(tokens=600_000, kind="writing"), "clear?")
        self.assertEqual(self.rec(tokens=600_000, kind="production"), "compact")
        self.assertEqual(self.rec(tokens=600_000, dirty=3), "compact")
        self.assertEqual(self.rec(tokens=600_000, runtime=["watcher on job 1 (pid 2)"]), "compact")

    def test_save_first_rule(self):
        sf = self.c.save_first
        self.assertEqual(sf(self.row()), "skip")
        self.assertEqual(sf(self.row(runtime=["1 child process(es)"])), "save-first")
        self.assertEqual(sf(self.row(kind="production")), "save-first")
        self.assertEqual(sf(self.row(kind="service")), "save-first")
        self.assertEqual(sf(self.row(kind="writing")), "skip")
        self.assertEqual(sf(self.row(dirty=2)), "save-first")
        self.assertEqual(sf(self.row(dirty=None)), "skip")       # not a git work tree

    def test_below_threshold_leave_even_for_coordinator(self):
        self.assertEqual(self.rec(tokens=10, kind="coordinator"), "leave")


class Report(Base):
    def test_report_changes_nothing_and_lists_the_command(self):
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.typed_keys(), [])
        self.assertIn("fleetcontext --compact alpha --go", out)
        self.assertIn("300k", out)

    def test_json(self):
        code, out = self.run_main("--json")
        data = json.loads(out)
        self.assertEqual(data["sessions"][0]["action"], "compact")
        self.assertEqual(data["sessions"][0]["save"], "skip")
        self.assertEqual(data["context"]["compact_above"], 250_000)

    def test_attach_client_is_not_a_row_and_its_session_is_manual(self):
        bg = "bbbbbbbb-0000-4000-8000-000000000002"
        self.procs = [(4242, self.cwd, ["claude", "attach", "bbbbbbbb"]),
                      (5000, self.cwd, ["claude", "--session-id", bg, "--fork-session"])]
        self.agents = [{"pid": 5000, "name": "alpha", "sessionId": bg, "kind": "background",
                        "status": "idle"}]
        code, out = self.run_main("--json")
        rows = json.loads(out)["sessions"]
        self.assertEqual([r["pid"] for r in rows], [5000])
        self.assertEqual(rows[0]["pane"], "%7")
        self.assertEqual(rows[0]["action"], "manual")


class CompactPreflight(Base):
    def blocked(self, *argv, text):
        code, out = self.run_main("--compact", "alpha", "--go", *argv)
        self.assertEqual(code, 2, out)
        self.assertIn(text, out)
        self.assertEqual(self.typed_keys(), [])

    def test_not_running(self):
        self.procs, self.agents = [], []
        self.blocked(text="no live session answers to 'alpha'")

    def test_duplicate(self):
        self.procs.append((4343, self.cwd, ["claude", "--name", "alpha"]))
        self.agents.append({"pid": 4343, "name": "alpha", "sessionId": "x", "kind": "interactive"})
        self.blocked(text="2 sessions answer")

    def test_self(self):
        self.replace_patch("SELF_UUID", mock.patch.object(self.c, "SELF_UUID", UUID))
        self.blocked(text="cannot type into its own pane")

    def test_self_by_process_ancestry(self):
        self.procs = [(os.getppid(), self.cwd, ["claude", "--name", "alpha"])]
        self.agents = [dict(self.agents[0], pid=os.getppid())]
        self.pane_pids = {os.getppid(): "%7"}
        self.blocked(text="cannot type into its own pane")

    def test_coordinator(self):
        self.brief("alpha", "Kind: coordinator\n")
        self.blocked(text="never scripted")

    def test_background(self):
        self.agents[0]["kind"] = "background"
        self.blocked(text="background session")

    def test_unverified_transcript(self):
        self.agents = None
        with mock.patch.object(self.c, "session_name",
                               return_value=("alpha", UUID, "UNVERIFIED: guess")):
            code, out = self.run_main("--compact", "alpha", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("transcript not verified", out)

    def test_no_pane(self):
        self.pane_pids = {}
        self.blocked(text="no tmux pane")

    def test_busy(self):
        self.screen = BUSY
        self.blocked(text="mid-turn")

    def test_busy_by_agent_status(self):
        self.agents[0]["status"] = "busy"
        self.blocked(text="mid-turn")

    def test_trust_prompt(self):
        self.screen = "Is this a project you created or one you trust?"
        self.blocked(text="folder-trust")

    def test_background_dialog(self):
        self.screen = "Background work is running\n  1. Exit and stop tasks\n"
        self.blocked(text="background-work dialog")

    def test_draft_in_input_line(self):
        self.screen = DRAFT
        self.blocked(text="already holds text")

    def test_no_input_line(self):
        self.screen = "  1. Yes\n  2. No\n"
        self.blocked(text="no input line")

    def test_save_first_blocks_until_saved(self):
        self.kids = [99]
        self.blocked(text="save-first (1 child process(es))")
        code, out = self.run_main("--compact", "alpha", "--go", "--saved")
        self.assertEqual(code, 0, out)
        self.assertIn("--saved given", out)

    def test_production_kind_is_save_first(self):
        self.brief("alpha", "Kind: production\n")
        self.blocked(text="kind production")

    def test_service_kind_is_save_first(self):
        self.brief("alpha", "Kind: service — owns a shared record\n")
        self.blocked(text="kind service")

    def test_live_registered_watcher_is_save_first(self):
        d = os.path.join(self.cfg.state, "watchers"); os.makedirs(d)
        json.dump({"session": "alpha", "job": "111111", "pid": 1, "starttime": "9"},
                  open(os.path.join(d, "a.json"), "w"))
        self.blocked(text="watcher on job 111111")

    def test_uncommitted_work_is_save_first(self):
        run = lambda *a: subprocess.run(["git", "-C", self.cwd, *a], capture_output=True, check=True)
        run("init", "-q")
        open(os.path.join(self.cwd, "f"), "w").write("x")
        self.blocked(text="1 uncommitted path(s)")

    def test_below_threshold_is_only_a_note(self):
        self.stats["tokens"] = 1_000
        code, out = self.run_main("--compact", "alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("below compact_above", out)


class Compact(Base):
    def test_plan_types_nothing(self):
        code, out = self.run_main("--compact", "alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("plan only", out)
        self.assertIn("/compact keep job ids, file paths, open decisions and commitments", out)
        self.assertEqual(self.typed_keys(), [])

    def test_go_types_focus_then_enter_and_confirms_the_boundary(self):
        code, out = self.run_main("--compact", "alpha", "--go")
        self.assertEqual(code, 0, out)
        keys = self.typed_keys()
        self.assertEqual(keys[0], ("send-keys", "-t", "%7", "-l",
                                   "/compact keep job ids, file paths, open decisions and commitments"))
        self.assertEqual(keys[1], ("send-keys", "-t", "%7", "Enter"))
        self.assertIn("compacted alpha: 300k -> 9k", out)

    def test_existing_boundaries_do_not_count(self):
        self.boundaries = [{"pre": 1, "post": 1}]
        self.compacts_on_enter = False
        code, out = self.run_main("--compact", "alpha", "--go", "--wait", "30")
        self.assertEqual(code, 4, out)
        self.assertIn("no new compaction boundary", out)


    def test_focus_text_comes_from_config(self):
        self.cfg.close()
        self.toml = BASE_TOML + '\n[context]\ncompact_focus = "keep the manuscript outline"\n'
        self.setUp()
        code, out = self.run_main("--compact", "alpha", "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.typed_keys()[0][-1], "/compact keep the manuscript outline")

    def test_corrupted_input_line_is_cleared_and_not_entered(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            if a[0] == "send-keys" and "-l" in a:
                self.screen = f"{RULE}\n❯ 8;32;42;52c{a[-1]}\n{RULE}\n"
            return r
        self.tmux = tmux
        code, out = self.run_main("--compact", "alpha", "--go")
        self.assertEqual(code, 3, out)
        self.assertIn(("send-keys", "-t", "%7", "C-u"), self.calls)
        self.assertNotIn(("send-keys", "-t", "%7", "Enter"), self.calls)

    def test_session_exiting_mid_compaction_stops_with_3(self):
        self.compacts_on_enter = False
        self.replace_patch("alive", mock.patch.object(self.c, "alive", return_value=False))
        code, out = self.run_main("--compact", "alpha", "--go")
        self.assertEqual(code, 3, out)
        self.assertIn("exited while compacting", out)


class Color(Base):
    def test_plan(self):
        code, out = self.run_main("--color", "alpha")
        self.assertEqual(code, 0, out)
        self.assertIn("type `/color red`", out)
        self.assertEqual(self.typed_keys(), [])

    def test_go_types_declared_color_and_confirms_the_record(self):
        code, out = self.run_main("--color", "alpha", "--go")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.typed_keys()[0], ("send-keys", "-t", "%7", "-l", "/color red"))
        self.assertIn("alpha is red", out)

    def test_already_that_color_does_nothing(self):
        self.color = "red"
        code, out = self.run_main("--color", "alpha", "--go")
        self.assertEqual(code, 0, out)
        self.assertIn("already red", out)
        self.assertEqual(self.typed_keys(), [])

    def test_no_declared_color_blocks(self):
        self.procs = [(4242, self.cwd, ["claude", "--name", "gamma"])]
        self.agents = [dict(self.agents[0], name="gamma")]
        code, out = self.run_main("--color", "gamma", "--go")
        self.assertEqual(code, 2, out)
        self.assertIn("no [colors] entry for gamma", out)

    def test_coordinator_may_be_colored(self):
        self.brief("alpha", "Kind: coordinator\n")
        code, out = self.run_main("--color", "alpha", "--go")
        self.assertEqual(code, 0, out)

    def test_record_that_never_appears_exits_4(self):
        orig = self.tmux
        def tmux(*a):
            r = orig(*a)
            self.color = None
            return r
        self.tmux = tmux
        code, out = self.run_main("--color", "alpha", "--go")
        self.assertEqual(code, 4, out)


if __name__ == "__main__":
    unittest.main()
