import os, tempfile, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

class CorrectedLabel(unittest.TestCase):
    """The @repo label vs the pane title. OBSERVED 2026-09-13: a session at the
    trust prompt, before claude had set its title, had its good label replaced by
    the shell's title, and the manifest named a session after a host and path."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmp = tempfile.TemporaryDirectory()
        self.snap = load_tool("fleetsnap")
        self.p = mock.patch.object(self.snap, "PROJECTS", self.tmp.name)
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

if __name__ == "__main__":
    unittest.main()
