import json, os, shutil, tempfile, unittest
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

    def brief(self, name, text):
        with open(os.path.join(self.cfg.config, "briefs", f"{name}.md"), "w") as f:
            f.write(text)

    def manifest(self, proc_cwd="/home/u/work", repo="alpha", title="title",
                 agents=None, transcript_name=None, fleet="testfleet", labels=None,
                 tsessions=None, extra_rows=()):
        # TWELVE fields: two labels, `@agent` and `@fleet`, then the pane's start
        # command. Each new one is appended, because that is what keeps the older
        # indices where their readers expect them -- this unpack has been left
        # behind by a moving format twice.
        def mkrow(label, pidx, tsess="fleet"):
            return [tsess, "1", "win", str(pidx), f"%{pidx + 1}", label, title,
                    "/home/u/somewhere-else", "100", "80x40", fleet, ""]
        # `labels` builds a MULTI-session fixture; one row stays the default, so
        # every test written against the single-pane shape is untouched.
        # `tsessions` gives those rows DIFFERENT tmux session names -- the shape a
        # capture spanning two servers has, which no fixture could express while
        # the name was a constant in this helper.
        rows = ([mkrow(l, i, tsessions[i] if tsessions else "fleet")
                 for i, l in enumerate(labels)] if labels
                else [mkrow(repo, 0)])
        rows += [list(r) for r in extra_rows]
        proc = {"pid": 200, "version": "2.1.276", "resume_uuid": None, "started": "",
                "argv": ["claude", "--name", "alpha"]}
        sn = self.snap
        with mock.patch.object(sn, "pane_rows", return_value=rows), \
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
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                sn.main()
            # Kept rather than discarded: what this tool PRINTS about the panes it
            # skipped is half of what it is for, and a test that only reads the
            # manifest cannot tell a reported omission from a silent one.
            self.out = buf.getvalue()
            with open(os.path.join(self.cfg.state, "manifest.json")) as f:
                return json.load(f)

    def test_another_fleets_pane_is_not_snapshotted(self):
        """A snapshot that quietly omits a session is a RESTORE that quietly omits
        it. Here the omission is right -- the pane is not ours -- and it still has
        to be said out loud, because the unlabeled case is indistinguishable from a
        session of ours stamped by a tool too old to label it."""
        snap = self.manifest(fleet="teaching")
        self.assertEqual(snap["sessions"], [])
        self.assertIn("not this fleet's panes", self.out)
        self.assertIn("@fleet=teaching", self.out)

    def test_an_unlabeled_pane_is_not_snapshotted_and_is_named(self):
        snap = self.manifest(fleet="")
        self.assertEqual(snap["sessions"], [])
        self.assertIn("@fleet=(unlabeled)", self.out)

    def test_cwd_comes_from_the_process(self):
        self.assertEqual(self.manifest()["sessions"][0]["cwd"], "/home/u/work")

    def test_pane_path_is_the_fallback(self):
        self.assertEqual(self.manifest(proc_cwd=None)["sessions"][0]["cwd"], "/home/u/somewhere-else")


class FurnitureIsRecordedButIsNotASession(SnapshotDirectory):
    """A pane in a fleet window that is not an agent: a board, a shell.

    `window_layouts` records the layout of every window verbatim and the docstring
    claimed it restored geometry exactly. It does not. A layout string describes
    every pane the window had, and `tmux select-layout` given one that describes
    more panes than the window holds exits 0, prints nothing, and leaves the
    default split -- measured 2026-11-23 with a 4-pane layout on a 2-pane window.
    So a window holding two agents and two pieces of furniture came back at 50/50
    whatever it had been hand-sized to, and nothing said so.

    Recording the furniture is what makes the pane count match again. It is
    recorded BESIDE the layout and never in `sessions`: a session has a brief, a
    color, a re-arm ledger and a restore obligation, and furniture has none of
    those. Landing in `sessions` would hand it every one of them.
    """

    def furn(self, pidx=1, start="", cwd="/home/u", pane="%9", win="1",
             tsess="fleet", agent="", fleet=""):
        return [tsess, win, "win", str(pidx), pane, agent, "title", cwd,
                "100", "80x40", fleet, start]

    def test_a_pane_with_neither_label_in_a_fleet_window_is_furniture(self):
        snap = self.manifest(extra_rows=[self.furn(
            pidx=1, start="/home/u/bin/fleetboard --watch", cwd="/home/u")])
        got = snap["window_layouts"]["fleet:1"]["furniture"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["start_command"], "/home/u/bin/fleetboard --watch")
        self.assertEqual(got[0]["cwd"], "/home/u")
        self.assertEqual(got[0]["pane_index"], 1)

    def test_it_is_not_a_session(self):
        """Not in `sessions`, and not in the count of them. A membership
        obligation it cannot meet would be demanded of it every run."""
        snap = self.manifest(extra_rows=[self.furn()])
        self.assertEqual([x["label"] for x in snap["sessions"]], ["alpha"])
        self.assertNotIn("furniture", str(snap["sessions"]))

    def test_a_plain_shell_records_an_empty_command_not_a_guessed_one(self):
        """`pane_start_command` is EMPTY for a pane created without one, and
        `pane_current_command` is not the fallback: it reads `python3` for a
        running board, which is not a command anything can relaunch."""
        snap = self.manifest(extra_rows=[self.furn(start="")])
        got = snap["window_layouts"]["fleet:1"]["furniture"][0]
        self.assertEqual(got["start_command"], "")
        self.assertIn("the default shell", self.out)

    def test_a_command_holding_a_tab_survives_the_row(self):
        """The one column that can contain the field separator, which is why it
        is last and joined rather than indexed."""
        snap = self.manifest(extra_rows=[self.furn(start="sh -c 'printf a\tb'")])
        self.assertEqual(
            snap["window_layouts"]["fleet:1"]["furniture"][0]["start_command"],
            "sh -c 'printf a\tb'")

    def test_furniture_outside_a_fleet_window_is_still_somebody_elses_pane(self):
        """`list-panes -a` crosses tmux sessions, so this tool sees the owner's
        own windows. Scoped the same way the window-name guard is: a scratch
        window is unlabeled BY DESIGN, and recording every pane in one is how a
        record gets trained into noise."""
        snap = self.manifest(extra_rows=[self.furn(win="7", pane="%40")])
        self.assertNotIn("fleet:7", snap["window_layouts"])
        self.assertIn("%40", self.out)
        self.assertIn("not this fleet's panes", self.out)

    def test_an_agent_without_a_fleet_label_is_not_furniture(self):
        """Ours, stamped by a tool too old to say so -- which needs a human, not
        a pane rebuilt from a recorded command."""
        snap = self.manifest(extra_rows=[self.furn(agent="beta", pane="%40")])
        self.assertNotIn("furniture", snap["window_layouts"].get("fleet:1", {}))
        self.assertIn("@fleet=(unlabeled)", self.out)

    def test_several_pieces_are_recorded_in_pane_order(self):
        """Layout strings map to panes by POSITION, so the order is the record."""
        snap = self.manifest(extra_rows=[self.furn(pidx=3, pane="%23"),
                                         self.furn(pidx=1, pane="%22")])
        got = snap["window_layouts"]["fleet:1"]["furniture"]
        self.assertEqual([f["pane_index"] for f in got], [1, 3])

    def test_the_report_says_a_restore_will_run_these_commands(self):
        """A restore executing a string read from a file is a new class of action
        for a tool that until now only ever launched `claude` from a versioned
        path. The snapshot that records the string says so."""
        self.manifest(extra_rows=[self.furn(start="/home/u/bin/fleetboard --watch")])
        self.assertIn("/home/u/bin/fleetboard --watch", self.out)
        self.assertIn("RUNS these commands", self.out)


class UnlabeledPane(SnapshotDirectory):
    """A pane launched as a bare `claude` and named later has no @repo. fleetsnap
    used to invent "(unlabeled %1)" and then ask for a brief under that name, while
    fleetupgrade resolved the session fine (OBSERVED 2026-09-18)."""
    def session(self, **kw):
        return self.manifest(repo="", **kw)["sessions"][0]

    def test_name_from_claude_agents(self):
        s = self.session(agents=[{"pid": 200, "name": "oldname"}])
        self.assertEqual(s["label"], "oldname")
        self.assertIn("claude agents", s["label_note"])
        self.assertEqual(s["membership_problems"][0]["kind"], "brief")   # named: normal checks

    def test_name_from_the_transcript_when_agents_cannot_be_read(self):
        s = self.session(agents=None, transcript_name="oldname")
        self.assertEqual(s["label"], "oldname")
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


class ThePaneRowIsAskedOfRealTmux(unittest.TestCase):
    """What the format asks tmux for, checked against tmux.

    Every other test here feeds `pane_rows` a hand-written fixture, so the format
    string itself is exercised nowhere: a column asking for the wrong thing, or
    for the right thing in the wrong place, would pass the whole suite. The
    arity check next door counts the fields and cannot see what is in them --
    proved by replacing `#{pane_start_command}` with `#{pane_id}` in a throwaway
    copy and watching the suite stay green.

    Run against a tmux server of this test's own, via `TMUX_TMPDIR`, never the
    caller's."""

    @unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
    def test_the_last_field_is_the_command_the_pane_was_created_with(self):
        import subprocess
        cfg = FakeConfig()
        tmpdir = tempfile.mkdtemp(prefix="ft", dir="/tmp")
        s = load_tool("fleetsnap")
        old = os.environ.get("TMUX_TMPDIR")
        os.environ["TMUX_TMPDIR"] = tmpdir
        was_tmux = os.environ.pop("TMUX", None)
        tm = lambda *a: subprocess.run(["tmux", "-L", "snaprows", *a],
                                       capture_output=True, text=True, timeout=10)
        try:
            first = tm("new-session", "-d", "-P", "-F", "#{pane_id}",
                       "-s", "rowtest").stdout.strip()
            tm("split-window", "-t", "rowtest:", "sleep 300")
            # By pane ID. `rowtest:.0` is not the first pane when
            # `pane-base-index` is 1, which it is in the owner's own tmux.conf --
            # the setting that put every session one pane to the left in the
            # 2026-09-30 restore.
            tm("set", "-p", "-t", first, "@agent", "alpha")
            tm("set", "-p", "-t", first, "@fleet", "testfleet")
            with mock.patch.object(s, "sh", lambda *a, **k: subprocess.run(
                    ["tmux", "-L", "snaprows", *a[1:]], capture_output=True,
                    text=True, **k).stdout):
                rows = [r for r in s.pane_rows() if r[0] == "rowtest"]
            self.assertEqual(len(rows), 2, rows)
            # By POSITION, not by index: `pane-base-index` is 1 in the owner's
            # own tmux.conf and 0 by default, and this test is not about that.
            rows.sort(key=lambda r: int(r[3]))
            plain, cmd = rows
            self.assertEqual(len(plain), 12,
                             "the row must carry every field the format asks for")
            self.assertEqual(plain[5], "alpha", "@agent moved")
            self.assertEqual(plain[10], "testfleet", "@fleet moved")
            self.assertEqual(plain[11], "",
                             "a pane created without a command has no start command")
            # The command is there, and it is the START command: the trap is
            # `pane_current_command`, which reads `sleep` here and `python3` for
            # a running board -- neither of them a command anything can relaunch.
            #
            # Matched loosely because tmux RENDERS the argv it was given and
            # quotes any word holding a space: 3.8 answers `"sleep 300"`, quotes
            # included. That rendering is the reason `fleetrestore` splits the
            # string instead of handing it back, and the restore end-to-end test
            # is what proves the round trip.
            self.assertIn("sleep 300", cmd[11])
            self.assertNotEqual(cmd[11], "sleep",
                                "that is pane_current_command, not the start one")
        finally:
            tm("kill-server")
            if old is None:
                os.environ.pop("TMUX_TMPDIR", None)
            else:
                os.environ["TMUX_TMPDIR"] = old
            if was_tmux is not None:
                os.environ["TMUX"] = was_tmux
            shutil.rmtree(tmpdir, ignore_errors=True)
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

    def test_attach_client_color_is_unknown_not_none(self):
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
    as unknown, which was correct behavior and therefore raised no alarm. A value
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
    these two are structural and behavioral instead.
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
        self.assertEqual(int(m.group(2)), names,
                         "the r[:N] slice and the names it binds disagree")
        # The LAST field is taken separately and JOINED, because it is a command
        # line and is the one column that can hold a tab of its own. So the tuple
        # is one shorter than the format by design -- and the tail has to begin
        # exactly where the tuple stopped, or a column is read twice or not at
        # all. Checked here rather than assumed, since "one shorter" is also what
        # a format that grew a field and left the unpack behind looks like.
        t = re.search(r'start = "\\t"\.join\(r\[(\d+):\]\)', unpack)
        self.assertIsNotNone(t, "the trailing field must be joined, not sliced off")
        self.assertEqual(int(t.group(1)), names,
                         "the joined tail must start where the unpack stopped")
        self.assertEqual(fields, names + 1,
                         "the format asks tmux for %d fields; the unpack names %d "
                         "and joins the rest into one" % (fields, names))

    def test_the_row_unpacks_to_the_fields_the_format_asks_for(self):
        """The defect this class exists for, in its post-retirement form: a row
        must unpack so that the NAME comes from the label field and nothing
        downstream reads a neighboring column by accident. The format has lost a
        field twice now -- the grouping, then the old name -- and each time every
        index after it moved."""
        row = ["0", "1", "win", "0", "%1", "alpha",
               "title", "/w", "123", "80x24", "testfleet", ""]
        (sess, win, winname, pidx, pane,
         agent, title, path, ppid, size, fleet) = row[:11]
        self.assertEqual("\t".join(row[11:]), "", "the start command is the tail")
        self.assertEqual(self.s.agent_label(agent), "alpha")
        self.assertEqual(self.s.fleet_label(fleet), "testfleet")
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
        """Order matters: `claude agents` is what tells an unlabeled pane of OURS
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


class TheCoordinatorIsNamedByItsBrief(SnapshotDirectory):
    """Which session coordinates is a fact about its ROLE, and the brief is the one
    place a role is written down. This used to be read off the session's NAME.

    `fleetsnap` had the right lookup -- `kind == "coordinator"` -- but no session
    record carried a `kind`, so it never matched and a fallback behind it took the
    session literally called `coord`. Two consequences, both silent: a fleet whose
    coordinator is called anything else had none, and a renamed coordinator would
    have handed the role to whatever took the old name. Meanwhile the key the
    lookup fed stopped being written on 2026-10-01, so `fleetrestore` printed
    `coordinator: ?` for six weeks with nothing to notice it (2026-11-12).
    """
    def coord(self, *labels_and_kinds):
        """labels_and_kinds: ("alpha", "repo"), ("lead", "coordinator"), ...

        A kind of None writes a brief that declares nothing, which is the shape of
        a brief somebody has not filled in yet."""
        for name, kind in labels_and_kinds:
            self.brief(name, f"# {name}\n" + (f"Kind: {kind}\n" if kind else ""))
        m = self.manifest(labels=[n for n, _ in labels_and_kinds])
        with open(os.path.join(self.cfg.state, "index.md")) as f:
            self.index = f.read()
        return m

    def test_the_manifest_records_the_coordinator(self):
        """The key `fleetrestore` prints. Its absence is what `?` was."""
        m = self.coord(("alpha", "repo"), ("beta", "coordinator"))
        self.assertIn("coordinator", m, "the key fleetrestore reads must be written")
        self.assertEqual(m["coordinator"], "beta")

    def test_the_coordinator_need_not_be_called_coord(self):
        """The case the old fallback could not see at all."""
        self.assertEqual(self.coord(("alpha", "repo"), ("beta", "coordinator"))
                         ["coordinator"], "beta")

    def test_a_session_called_coord_is_not_one_unless_its_brief_says_so(self):
        """The mirror, and the more dangerous half: the old fallback answered this
        with "coord" on the strength of the name alone."""
        m = self.coord(("coord", "repo"), ("alpha", "repo"))
        self.assertIsNone(m["coordinator"],
                          "the name is not evidence; the brief is")

    def test_every_session_records_the_kind_its_brief_declares(self):
        m = self.coord(("alpha", "repo"), ("beta", "coordinator"), ("gamma", None))
        self.assertEqual({s["label"]: s["kind"] for s in m["sessions"]},
                         {"alpha": "repo", "beta": "coordinator", "gamma": None})

    def test_two_claimants_record_none_rather_than_the_first(self):
        """Taking the first off the list would render a configuration mistake as a
        confident answer, and the answer would depend on pane order."""
        m = self.coord(("alpha", "coordinator"), ("beta", "coordinator"))
        self.assertIsNone(m["coordinator"])
        self.assertIn("2 briefs declare", self.out)
        self.assertIn("alpha", self.out)

    def test_the_index_says_which_of_the_two_absences_it_is(self):
        """They need opposite fixes -- write the line into a brief, or take it out
        of all but one -- so one shared `_none_` is not enough."""
        self.coord(("alpha", "repo"), ("beta", "repo"))
        self.assertIn("no brief declares", self.index)
        self.coord(("alpha", "coordinator"), ("beta", "coordinator"))
        self.assertIn("each declare", self.index)

    def test_the_index_names_the_coordinator_and_says_on_what_evidence(self):
        self.coord(("alpha", "repo"), ("beta", "coordinator"))
        self.assertIn("Coordinator: **beta**", self.index)
        self.assertIn("brief", self.index)

    def test_the_manifest_this_tool_writes_is_the_one_fleetrestore_reads(self):
        """The handoff, run end to end, because testing each side against its own
        fixture is what hid this for six weeks.

        `fleetrestore`'s own tests hand-write a manifest, and that fixture kept
        carrying `"coordinator": "coord"` for the entire time the producer wrote no
        such key -- so both suites were green and the live tool printed `?` on every
        run. Nothing here is hand-written: `fleetsnap` above produced the file, and
        the real `fleetrestore` binary reads that file and is asked what it says.
        A key renamed on either side fails this and nothing else.
        """
        import subprocess, tempfile, shutil
        self.coord(("alpha", "repo"), ("beta", "coordinator"))
        tmux = tempfile.mkdtemp(prefix="ftmux", dir="/tmp")
        home = os.path.join(tmux, "nohome")       # no version store: bare `claude`
        os.makedirs(home, exist_ok=True)
        try:
            env = dict(os.environ, FLEET_CONFIG=self.cfg.config,
                       TMUX_TMPDIR=tmux, HOME=home)
            env.pop("TMUX", None)
            r = subprocess.run([os.path.join(APP, "bin", "fleetrestore")],
                               capture_output=True, text=True, env=env)
        finally:
            shutil.rmtree(tmux, ignore_errors=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        line = next(x for x in r.stdout.splitlines() if "coordinator:" in x)
        self.assertIn("beta", line)
        self.assertNotIn("?", line, "the key the producer writes must be the key "
                                    "the consumer reads")


class TheRebuildSnippetNamesTheSessionItCaptured(SnapshotDirectory):
    """`manifest.md` carries hand instructions for rebuilding from a plain shell,
    and they used to open with a literal `tmux new-session -d -s 0`.

    That literal was right only for as long as nobody renamed the tmux session --
    and the rename was under discussion when this was written. A reader following
    a stale snippet would have built a second session beside the real one and
    found an empty fleet in it, which is the failure this file exists to prevent:
    recovery instructions that look authoritative and point somewhere else."""

    def md(self):
        with open(os.path.join(self.cfg.state, "manifest.md")) as f:
            return f.read()

    def test_the_new_session_line_uses_the_captured_name(self):
        self.manifest()                      # fixture captures session "fleet"
        self.assertIn("tmux new-session -d -s fleet", self.md())

    def test_no_literal_zero_is_written(self):
        self.manifest()
        self.assertNotIn("-s 0", self.md())

    def test_it_also_says_how_to_attach(self):
        """The snippet told a reader how to BUILD the session and not how to enter
        it, which is the question actually being asked at that moment."""
        self.manifest()
        self.assertIn("tmux attach -t fleet", self.md())

    def test_a_capture_spanning_two_servers_names_neither(self):
        """Two session names and the snippet picks one: half the rebuild lands in
        the wrong place. A placeholder is useless in the honest way."""
        self.manifest(labels=["alpha", "beta"], tsessions=["one", "two"])
        md = self.md()
        self.assertIn("-s <session>", md)
        self.assertNotIn("-s one", md)
        self.assertNotIn("-s two", md)
