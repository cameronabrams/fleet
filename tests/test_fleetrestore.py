import json, os, shutil, subprocess, tempfile, unittest
from tests.support import APP, BASE_TOML, FakeConfig

TOOL = os.path.join(APP, "bin", "fleetrestore")

def session(label, window, pane, fleet="f", uuid="u"):
    return {"label": label, "fleet": fleet, "cwd": "/tmp",
            "tmux": {"session": "0", "window": window, "window_name": fleet,
                     "pane_index": pane, "pane_id": "%1", "size": "80x24"},
            "resume_uuid": uuid, "resume_uuid_source": "verified: test",
            "durable_files": []}

class Plan(unittest.TestCase):
    """The plan is the default and must change nothing. Run against a private
    tmux socket directory with no server, so no real pane is read or touched."""
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML + '\n[spawn]\nenv = {{ NOTIFY = "1" }}\n')
        self.tmux = tempfile.mkdtemp(prefix="ftmux", dir="/tmp")
        man = {"captured": "now", "installed_claude": "x", "fleet": "f",
               "coordinator": "coord",
               "sessions": [session("beta", 2, 1, uuid="u-beta"),
                            session("alpha", 2, 0, uuid="u-alpha"),
                            session("gamma", 3, 0, uuid="UNVER-x")]}
        man["sessions"][2]["resume_uuid_source"] = "UNVERIFIED: guess"
        for name in ("manifest", "f"):
            json.dump(man, open(os.path.join(self.cfg.state, f"{name}.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.tmux); self.cfg.close()

    def run_tool(self, *args):
        env = dict(os.environ, TMUX_TMPDIR=self.tmux); env.pop("TMUX", None)
        return subprocess.run([TOOL, *args], capture_output=True, text=True, env=env)

    def test_lists_fleets(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("f ", r.stdout)

    def test_plan_changes_nothing_and_resumes_in_pane_order(self):
        r = self.run_tool("f")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("PLAN (nothing executed", out)
        self.assertNotIn("  $ ", out)                       # executed commands are prefixed $
        self.assertIn("unverified resume targets", out)
        a = out.index("claude --name alpha --resume u-alpha")
        b = out.index("claude --name beta --resume u-beta")
        self.assertLess(a, b)                               # pane 0 before pane 1
        self.assertIn("NOTIFY=1 claude --name alpha", out)  # [spawn].env carried into a restore

    def test_unknown_fleet(self):
        r = self.run_tool("nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown fleet", r.stderr)

if __name__ == "__main__":
    unittest.main()
