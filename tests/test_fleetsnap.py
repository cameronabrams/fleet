import json, os, tempfile, unittest
from unittest import mock
from tests.support import APP, FakeConfig, load_tool
from fleet import transcripts

class SnapshotDirectory(unittest.TestCase):
    """The manifest's cwd is what fleetrestore rebuilds a pane in, so it must be the
    SESSION's directory. tmux's pane_current_path follows whatever the pane runs."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.snap = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def manifest(self, proc_cwd="/home/u/work", repo="alpha", title="title",
                 agents=None, transcript_name=None):
        # ten fields: one label, `@agent`; the grouping and the old name retired
        row = ["fleet", "1", "win", "0", "%1", repo, title,
               "/home/u/somewhere-else", "100", "80x40"]
        proc = {"pid": 200, "version": "2.1.276", "resume_uuid": None, "started": "",
                "argv": ["claude", "--name", "alpha"]}
        sn = self.snap
        with mock.patch.object(sn, "pane_rows", return_value=[row]), \
             mock.patch.object(sn, "claude_proc", return_value=proc), \
             mock.patch.object(sn, "list_agents", return_value=agents), \
             mock.patch.object(sn, "session_name", return_value=(transcript_name, None, "x")), \
             mock.patch.object(sn, "newest_transcript", return_value=(None, "UNVERIFIED")), \
             mock.patch.object(sn, "proc_cwd", side_effect=lambda pid: proc_cwd), \
             mock.patch.object(sn, "resume_handle", return_value=(None, "UNVERIFIED: test")), \
             mock.patch.object(sn, "durable_files", return_value=[]), \
             mock.patch.object(sn, "agent_color", return_value=None), \
             mock.patch.object(sn, "window_layouts", return_value={}), \
             mock.patch.object(sn, "window_meta", return_value={}), \
             mock.patch.object(sn, "prior_snapshot", return_value={}), \
             mock.patch.object(sn, "linger_units", return_value=[]), \
             mock.patch.object(sn, "keep_real_window_names", return_value=[]), \
             mock.patch.object(sn, "rotate"), \
             mock.patch.object(sn.sys, "argv", ["fleetsnap"]):
            import contextlib, io, json
            with contextlib.redirect_stdout(io.StringIO()):
                sn.main()
            with open(os.path.join(self.cfg.state, "manifest.json")) as f:
                return json.load(f)

    def test_cwd_comes_from_the_process(self):
        self.assertEqual(self.manifest()["sessions"][0]["cwd"], "/home/u/work")

    def test_pane_path_is_the_fallback(self):
        self.assertEqual(self.manifest(proc_cwd=None)["sessions"][0]["cwd"], "/home/u/somewhere-else")


class UnlabelledPane(SnapshotDirectory):
    """A pane launched as a bare `claude` and named later has no @repo. fleetsnap
    used to invent "(unlabeled %1)" and then ask for a brief under that name, while
    fleetupgrade resolved the session fine (OBSERVED 2026-09-18)."""
    def session(self, **kw):
        return self.manifest(repo="", **kw)["sessions"][0]

    def test_name_from_claude_agents(self):
        s = self.session(agents=[{"pid": 200, "name": "literature"}])
        self.assertEqual(s["label"], "literature")
        self.assertIn("claude agents", s["label_note"])
        self.assertEqual(s["membership_problems"][0]["kind"], "brief")   # named: normal checks

    def test_name_from_the_transcript_when_agents_cannot_be_read(self):
        s = self.session(agents=None, transcript_name="literature")
        self.assertEqual(s["label"], "literature")
        self.assertIn("transcript", s["label_note"])

    def test_every_recorded_session_has_a_name(self):
        """The invariant the dead branch used to hedge against. fleetrestore needs
        a name for `--name` and for the brief, so a nameless row cannot be
        relaunched; now none is written. Checked against a manifest built with the
        hardest case present -- a pane with no label at all."""
        m = self.manifest(repo="", agents=[], transcript_name=None)
        self.assertTrue(all(s.get("label") for s in m["sessions"]),
                        [s.get("label") for s in m["sessions"]])
        self.assertNotIn("@repo", json.dumps(m),
                         "nothing may tell a reader to set the retired option")

    def test_a_pane_nothing_can_name_is_somebody_else_s_window(self):
        """No label, and neither `claude agents` nor the transcript names it. That
        is the shape of the owner's own window -- the personal session excluded on
        2026-09-30 had no CCP_AGENT and so no agents entry -- and it is no longer
        recorded as a nameless session of ours. It is still REPORTED: the snapshot
        says which panes it left out and why."""
        m = self.manifest(repo="", agents=[], transcript_name=None)
        self.assertEqual(m["sessions"], [],
                         "a pane nothing can name must not get a manifest entry")
        self.assertNotIn("unlabeled", json.dumps(m))


class CorrectedLabel(unittest.TestCase):
    """The @repo label vs the pane title. OBSERVED 2026-09-13: a session at the
    trust prompt, before claude had set its title, had its good label replaced by
    the shell's title, and the manifest named a session after a host and path."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmp = tempfile.TemporaryDirectory()
        self.snap = load_tool("fleetsnap")
        self.p = mock.patch.object(transcripts, "PROJECTS", self.tmp.name)
        self.p.start()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup(); self.cfg.close()

    def label(self, repo, title, argv=("claude", "--name", "fleet-repo")):
        return self.snap.corrected_label(repo, title, list(argv), "/home/u/Git/fleet")

    def test_shell_title_does_not_replace_label(self):
        self.assertEqual(self.label("fleet-repo", "user@host.example.edu:~/Git/fleet"),
                         ("fleet-repo", None))

    def test_bare_hostname_title_does_not_replace_label(self):
        # what tmux showed for a claude stuck at the trust prompt (no shell ran)
        self.assertEqual(self.label("fleet-repo", "host.example.edu"), ("fleet-repo", None))
        self.assertEqual(self.label("fleet-repo", "myhost"), ("fleet-repo", None))

    def test_ai_title_does_not_replace_label(self):
        self.assertEqual(self.label("fleet-repo", "✳ Fixing the slug bug"),
                         ("fleet-repo", None))

    def test_agreeing_title(self):
        self.assertEqual(self.label("fleet-repo", "✳ fleet-repo"), ("fleet-repo", None))

    def test_launch_name_corrects_stale_label(self):
        label, note = self.label("old-name", "fleet-repo")
        self.assertEqual(label, "fleet-repo")
        self.assertIn("old-name", note)

    def test_rename_recorded_in_transcript_corrects_label(self):
        # launched as old-name, then /rename -> new-name: argv still says old-name,
        # the transcript's last agentName says new-name.
        d = os.path.join(self.tmp.name, "-home-u-Git-fleet")
        os.makedirs(d)
        with open(os.path.join(d, "aaaaaaaa-0000-4000-8000-000000000001.jsonl"), "w") as f:
            f.write('{"type":"agent-name","agentName":"old-name"}\n'
                    '{"type":"agent-name","agentName":"new-name"}\n')
        label, _ = self.label("old-name", "new-name", ("claude", "--name", "old-name"))
        self.assertEqual(label, "new-name")

    def test_unconfirmed_name_like_title_keeps_label(self):
        # looks like a session name, but neither argv nor any transcript says so
        self.assertEqual(self.label("fleet-repo", "somebody-else"), ("fleet-repo", None))


class WindowNames(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.snap = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def test_auto_name_does_not_overwrite_prior_real_name(self):
        meta = {"0:1": {"name": "claude", "auto": True, "layout": "x"}}
        prior = {"window_layouts": {"0:1": {"name": "pestle", "layout": "x"}}}
        notes = self.snap.keep_real_window_names(meta, prior, {"0:1"})
        self.assertEqual(meta["0:1"]["name"], "pestle")
        self.assertEqual(len(notes), 1)

    def test_scratch_windows_are_not_warned_about(self):
        meta = {"0:9": {"name": "bash", "auto": True, "layout": "x"}}
        self.assertEqual(self.snap.keep_real_window_names(meta, {}, {"0:1"}), [])
        self.assertEqual(meta["0:9"]["name"], "bash")

    def test_deliberate_name_is_left_alone(self):
        meta = {"0:1": {"name": "mine", "auto": False, "layout": "x"}}
        prior = {"window_layouts": {"0:1": {"name": "old", "layout": "x"}}}
        self.assertEqual(self.snap.keep_real_window_names(meta, prior, {"0:1"}), [])
        self.assertEqual(meta["0:1"]["name"], "mine")


class Rotate(unittest.TestCase):
    def test_keeps_newest_n(self):
        cfg = FakeConfig()
        try:
            snap = load_tool("fleetsnap")
            p = os.path.join(cfg.state, "manifest.json")
            for i in range(4):
                open(f"{p}.bak-2026090{i}-000000", "w").close()
            open(p, "w").write("{}")
            dest = snap.rotate(p, keep=2)
            baks = sorted(x for x in os.listdir(cfg.state) if ".bak-" in x)
            self.assertEqual(len(baks), 2)
            self.assertIn(os.path.basename(dest), baks)
            self.assertIsNone(snap.rotate(os.path.join(cfg.state, "absent.json")))
        finally:
            cfg.close()


class Arguments(unittest.TestCase):
    """fleetsnap takes no arguments. It used to ignore them, so `fleetsnap --help`
    took a real snapshot and wrote the state directory (2026-09-13)."""
    def run_tool(self, *args):
        import subprocess
        from tests.support import APP
        cfg = FakeConfig()
        env = dict(os.environ, TMUX_TMPDIR=tempfile.mkdtemp(prefix="ft", dir="/tmp"))
        env.pop("TMUX", None)
        try:
            r = subprocess.run([os.path.join(APP, "bin", "fleetsnap"), *args],
                               capture_output=True, text=True, env=env)
            return r, os.listdir(cfg.state)
        finally:
            import shutil
            shutil.rmtree(env["TMUX_TMPDIR"]); cfg.close()

    def test_help_writes_nothing(self):
        r, written = self.run_tool("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("fleetsnap", r.stdout)
        self.assertEqual(written, [])

    def test_unknown_argument_refused(self):
        r, written = self.run_tool("--dry-run")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(written, [])


class StoppedProblems(unittest.TestCase):
    def setUp(self):
        from tests.support import BASE_TOML
        self.cfg = FakeConfig(toml=BASE_TOML +
            '\n[parked.alpha]\nuuid = "aaaaaaaa-0000-4000-8000-000000000001"\nsince = "2026-09-13"\n')
        self.snap = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def test_live_session_resuming_a_parked_transcript(self):
        p = self.snap.stopped_problems("alpha", "aaaaaaaa-0000-4000-8000-000000000001")
        self.assertEqual(len(p), 1)
        self.assertIn("will not relaunch", p[0][1])

    def test_name_reused_with_another_transcript(self):
        p = self.snap.stopped_problems("alpha", "dddddddd-0000-4000-8000-000000000004")
        self.assertEqual(len(p), 1)
        self.assertIn("name is [parked]", p[0][1])

    def test_unrelated_session(self):
        self.assertEqual(self.snap.stopped_problems("beta", "eeeeeeee-0000-4000-8000-000000000005"), [])


class LiveColor(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.snap = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def test_attach_client_colour_is_unknown_not_none(self):
        with mock.patch.object(self.snap, "agent_color", return_value=None):
            self.assertEqual(self.snap.live_color(["claude", "attach", "b20bc72b"], "b20bc72b-x"), (None, False))
            self.assertEqual(self.snap.live_color(["claude", "--name", "a", "--resume", "u"], "u"), (None, True))
        with mock.patch.object(self.snap, "agent_color", return_value="cyan"):
            self.assertEqual(self.snap.live_color(["claude", "--name", "a"], "u"), ("cyan", True))
        self.assertEqual(self.snap.live_color(["claude", "--name", "a"], None)[1], False)

class StateDirectoryNamespace(unittest.TestCase):
    """No tool may claim `<state>/*.json`. The state directory is shared.

    `fleetsnap` used to end each run by moving aside every `.json` in the state
    directory not named after a live fleet. The docstring said "per-fleet
    manifests"; the glob said `*.json`, and a file written by a different tool is
    indistinguishable from a dead fleet's manifest. On 2026-10-03 it renamed
    another tool's cache and that tool went blind -- rendering the missing values
    as unknown, which was correct behaviour and therefore raised no alarm. A value
    that used to be there is a different event from one that never arrived, and
    only the second is what "unknown" is designed to say.

    The cleanup is gone rather than narrowed: nothing writes `<fleet>.json` any
    more, so no residue can accumulate, and a migration that cannot have work left
    is only a blast radius. This test is what stops the next one.
    """

    # A line is bad if it matches every entry in the state directory ROOT. A
    # subdirectory is fine: `STATE/watchers/*.json` is owned by the watcher
    # registry, and the tool whose cache was renamed fixed itself the same way,
    # by moving under `STATE/cache/`. Ownership is the whole remedy -- the root
    # is shared, so nothing may sweep it.
    ROOT_SWEEP = [
        r'\{STATE\}/\*',                      # f"{STATE}/*.json"
        r'STATE\s*\+\s*f?[\'"]/\*',             # STATE + "/*.json"
        r'join\(\s*STATE\s*,\s*f?[\'"]\*',     # os.path.join(STATE, "*.json")
        r'listdir\(\s*STATE\s*\)',             # os.listdir(STATE)
        r'listdir\(\s*f?[\'"]\{STATE\}[\'"]\s*\)',
        r'(glob|listdir)\([^)]*state_dir\(\)[^)]*\)\s*$',
    ]

    def test_no_tool_sweeps_the_state_directory_root(self):
        import os, re
        from tests.support import APP
        bad = []
        for tool in sorted(os.listdir(os.path.join(APP, "bin"))):
            path = os.path.join(APP, "bin", tool)
            if not os.path.isfile(path):
                continue
            try:
                src = open(path).read()
            except (OSError, UnicodeDecodeError):
                continue
            for n, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if any(re.search(pat, line) for pat in self.ROOT_SWEEP):
                    bad.append(f"{tool}:{n}: {line.strip()}")
        self.assertEqual(bad, [],
                         "a tool is matching every entry in the shared state "
                         "directory root; own a subdirectory instead")

    def test_the_check_catches_the_forms_it_claims_to(self):
        """The guard is a source regex, which is the kind that passes because it
        matched nothing. Its first version looked only for a `*` and so missed
        `os.listdir(STATE)` -- same blast radius, different spelling, reported
        clean. These are the forms it must catch and the ones it must not."""
        import re
        catches = ['    for p in glob.glob(f"{STATE}/*.json"):',
                   '    for p in glob.glob(f"{STATE}/*"):',
                   '    for p in os.listdir(STATE):',
                   '    for p in glob.glob(STATE + "/*.json"):',
                   '    for p in glob.glob(os.path.join(STATE, "*.json")):']
        allows = ['    for p in glob.glob(os.path.join(STATE, "watchers", "*.json")):',
                  '    for p in glob.glob(f"{STATE}/watchers/*.json"):',
                  '    for p in glob.glob(WATCHDIR + "/*.json"):',
                  '    for old in sorted(glob.glob(f"{path}.bak-*"))[:-keep]:']
        for line in catches:
            self.assertTrue(any(re.search(pat, line) for pat in self.ROOT_SWEEP),
                            f"must be caught: {line.strip()}")
        for line in allows:
            self.assertFalse(any(re.search(pat, line) for pat in self.ROOT_SWEEP),
                             f"must be allowed: {line.strip()}")

    def test_fleetsnap_writes_only_its_own_files(self):
        """What it leaves behind, named. Anything else in the state directory
        belongs to another tool and is not fleetsnap's to move."""
        src = open(os.path.join(APP, "bin", "fleetsnap")).read()
        self.assertNotIn("retire_stale", src.replace("`retire_stale`", ""))
        self.assertNotIn("os.replace(path, dest)", src)



class FormatMatchesItsUnpack(unittest.TestCase):
    """A positional `list-panes -F` and the tuple that unpacks it are ONE thing.

    2026-10-01: the format moved from `@repo`,`@fleet` to `@agent`,`@repo` and the
    unpack was left at two names, so the variable called `fleet` held the agent
    name. One snapshot then recorded fourteen sessions in fourteen fleets and
    overwrote the real per-fleet manifests. Nothing failed: membership still
    worked, labels were still right, and the output was plausible.

    The test that existed asserted the format STRING contained `#{@agent}`. It
    passed throughout. A token check cannot see a positional shift, which is why
    these two are structural and behavioural instead.
    """
    def setUp(self):
        self.cfg = FakeConfig()
        self.s = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def test_the_field_count_equals_the_unpack_arity(self):
        """Count the elements joined by the tab, not the `#{...}` tokens: the size
        field is `#{pane_width}x#{pane_height}`, two tokens in ONE field. Counting
        tokens says 13 where tmux returns 12 -- a check that is wrong by one for
        ever, which would either cry wolf or be "fixed" by breaking the code to
        match it."""
        import ast, inspect, re
        src = inspect.getsource(self.s.pane_rows)
        tree = ast.parse(src.strip())
        joins = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "join"]
        self.assertEqual(len(joins), 1, "expected one '\\t'.join(...) in pane_rows")
        fields = len(joins[0].args[0].elts)
        unpack = inspect.getsource(self.s.snapshot) if hasattr(self.s, "snapshot") else \
                 open(os.path.join(APP, "bin", "fleetsnap")).read()
        m = re.search(r"\(sess, win, winname, pidx, pane,\s*\n\s*([^)]*)\) = r\[:(\d+)\]",
                      unpack)
        self.assertIsNotNone(m, "could not find the pane-row unpack")
        names = 5 + len([n for n in m.group(1).split(",") if n.strip()])
        self.assertEqual(fields, names,
                         "the format asks tmux for %d fields and the unpack names %d"
                         % (fields, names))
        self.assertEqual(int(m.group(2)), fields,
                         "the r[:N] slice must match the field count")

    def test_the_row_unpacks_to_the_fields_the_format_asks_for(self):
        """The defect this class exists for, in its post-retirement form: a row
        must unpack so that the NAME comes from the label field and nothing
        downstream reads a neighbouring column by accident. The format has lost a
        field twice now -- the grouping, then the old name -- and each time every
        index after it moved."""
        row = ["0", "1", "win", "0", "%1", "alpha",
               "title", "/w", "123", "80x24"]
        (sess, win, winname, pidx, pane,
         agent, title, path, ppid, size) = row[:10]
        self.assertEqual(self.s.agent_label(agent), "alpha")
        self.assertEqual((title, path, size), ("title", "/w", "80x24"),
                         "a shifted unpack shows up here first")

    def test_a_pane_is_ours_when_it_carries_the_label(self):
        self.assertTrue(self.s.is_agent_pane("alpha"))
        self.assertFalse(self.s.is_agent_pane(""))


class OutsidePanes(unittest.TestCase):
    """A pane with no `@agent` label is not this fleet's. Without the check,
    `fleet = fleet or sess` named it after its tmux session and wrote a manifest
    offering to restore something that was never ours."""

    def setUp(self):
        self.cfg = FakeConfig()
        self.s = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def test_membership_is_the_label_not_the_tmux_session_name(self):
        self.assertTrue(self.s.is_agent_pane("coord"))
        self.assertFalse(self.s.is_agent_pane(""))

    def test_the_name_is_resolved_before_membership_is_decided(self):
        """Order matters: `claude agents` is what tells an unlabelled pane of OURS
        from somebody else's window, so resolve_label has to run first. Reversed,
        a session named only by the platform would be dropped from recovery."""
        src = open(os.path.join(APP, "bin", "fleetsnap")).read()
        i = src.index("label, label_note = resolve_label(")
        j = src.index("if not is_agent_pane(label):")
        self.assertLess(i, j, "resolve_label must run before the membership check")
        self.assertNotIn("is_agent_pane(agent)", src,
                         "the check must take the RESOLVED label, not the raw pane "
                         "option -- a pane named only by `claude agents` carries "
                         "no option and would be dropped")


if __name__ == "__main__":
    unittest.main()
