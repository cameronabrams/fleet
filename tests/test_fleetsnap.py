import os, tempfile, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool
from fleet import transcripts

class SnapshotDirectory(unittest.TestCase):
    """The manifest's cwd is what fleetrestore rebuilds a pane in, so it must be the
    SESSION's directory. tmux's pane_current_path follows whatever the pane runs."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.snap = load_tool("fleetsnap")

    def tearDown(self):
        self.cfg.close()

    def manifest(self, proc_cwd="/home/u/work"):
        row = ["fleet", "1", "win", "0", "%1", "alpha", "grp", "title",
               "/home/u/somewhere-else", "100", "80x40"]
        proc = {"pid": 200, "version": "2.1.276", "resume_uuid": None, "started": "",
                "argv": ["claude", "--name", "alpha"]}
        sn = self.snap
        with mock.patch.object(sn, "pane_rows", return_value=[row]), \
             mock.patch.object(sn, "claude_proc", return_value=proc), \
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

if __name__ == "__main__":
    unittest.main()
