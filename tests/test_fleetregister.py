import glob, json, os, subprocess, sys, unittest
from tests.support import APP, FakeConfig

TOOL = os.path.join(APP, "bin", "fleetregister")

class Register(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.watch = os.path.join(self.cfg.state, "watchers")
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.cfg.close()

    def run_tool(self, *args):
        return subprocess.run([TOOL, *map(str, args)], capture_output=True, text=True,
                              env=dict(os.environ))

    def test_register_then_clear_only_after_exit(self):
        r = self.run_tool("alpha", "123456", self.proc.pid, "a note")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = glob.glob(self.watch + "/alpha-123456-*.json")
        self.assertEqual(len(files), 1)
        rec = json.load(open(files[0]))
        self.assertEqual((rec["session"], rec["job"], rec["pid"]), ("alpha", "123456", self.proc.pid))
        self.assertTrue(rec["starttime"].isdigit())

        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 1)
        self.assertIn("still alive", r.stderr)
        self.assertTrue(os.path.exists(files[0]))

        self.proc.kill(); self.proc.wait()
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(files[0]))

    def test_register_dead_pid_refused(self):
        self.proc.kill(); self.proc.wait()
        r = self.run_tool("alpha", "123456", self.proc.pid)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(glob.glob(self.watch + "/*.json"), [])

    def test_clear_nothing_registered(self):
        self.assertEqual(self.run_tool("--clear", "alpha", "999999").returncode, 1)

    def test_clear_with_reused_pid_clears(self):
        # registration names a live pid but a different starttime: the watcher is gone
        os.makedirs(self.watch, exist_ok=True)
        path = os.path.join(self.watch, f"alpha-123456-{self.proc.pid}.json")
        json.dump({"session": "alpha", "job": "123456", "pid": self.proc.pid,
                   "starttime": "1"}, open(path, "w"))
        r = self.run_tool("--clear", "alpha", "123456")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(path))

if __name__ == "__main__":
    unittest.main()
