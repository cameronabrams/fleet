import json, os, subprocess, sys, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool

class Base(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig()
        self.w = load_tool("fleetwatch")

    def tearDown(self):
        self.cfg.close()


class Owners(Base):
    def test_first_match_wins(self):
        self.assertEqual(self.w.owner_of("/scratch/proj-a-sweep/run1"), "alpha-runs")
        self.assertEqual(self.w.owner_of("/scratch/proj-a/build"), "alpha")

    def test_unmatched_is_never_guessed(self):
        self.assertEqual(self.w.owner_of("/scratch/other"), "UNATTRIBUTED")


SQUEUE_OK = """\
23225789|PENDING|JobHeldUser|2
23330046|RUNNING|None|3
23330046|PENDING|Priority|4
--WD--
23225789|/scratch/proj-a-sweep/ex17
23330046|/scratch/elsewhere
--END--
"""

class LiveJobs(Base):
    def jobs(self, out):
        with mock.patch.object(self.w, "sh", return_value=out):
            return self.w.live_jobs()

    def test_parses_tasks_states_owner_and_held(self):
        jobs, ok = self.jobs(SQUEUE_OK)
        self.assertTrue(ok)
        self.assertEqual(jobs["23225789"]["tasks"], 2)
        self.assertTrue(jobs["23225789"]["held"])
        self.assertEqual(jobs["23225789"]["owner"], "alpha-runs")
        j = jobs["23330046"]
        self.assertEqual((j["tasks"], j["states"]), (7, {"RUNNING": 3, "PENDING": 4}))
        self.assertFalse(j["held"])          # Priority starts on its own: needs a watcher
        self.assertEqual(j["owner"], "UNATTRIBUTED")

    def test_failed_ssh_is_not_no_work(self):
        # a banner and nothing else: must read as a FAILED query, not an empty queue
        jobs, ok = self.jobs("Welcome to the cluster\n")
        self.assertEqual(jobs, {})
        self.assertFalse(ok)

    def test_empty_queue_is_ok(self):
        self.assertEqual(self.jobs("--WD--\n--END--\n"), ({}, True))

    def test_final_states(self):
        with mock.patch.object(self.w, "sh", return_value="1|COMPLETED,\n2|\n--END--\n"):
            self.assertEqual(self.w.final_states({"1", "2"}), {"1": {"COMPLETED"}, "2": set()})
        with mock.patch.object(self.w, "sh", return_value=""):
            self.assertIsNone(self.w.final_states({"1"}))
        self.assertEqual(self.w.final_states(set()), {})


def starttime(pid):
    raw = open(f"/proc/{pid}/stat").read()
    return raw[raw.rindex(")") + 2:].split()[19]

class Alive(Base):
    def test_live_process_with_matching_identity(self):
        me = os.getpid()
        self.assertTrue(self.w.alive(me))
        self.assertTrue(self.w.alive(me, starttime(me)))

    def test_reused_pid_is_not_alive(self):
        self.assertFalse(self.w.alive(os.getpid(), "1"))

    def test_gone_pid(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
        self.assertFalse(self.w.alive(p.pid))

    def test_zombie_is_not_alive(self):
        # kill -0 succeeds on a zombie; alive() must not
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        for _ in range(100):
            try:
                if open(f"/proc/{p.pid}/stat").read().rsplit(")", 1)[1].split()[0] == "Z":
                    break
            except OSError:
                break
            import time; time.sleep(0.02)
        os.kill(p.pid, 0)                       # addressable ...
        self.assertFalse(self.w.alive(p.pid))  # ... but not alive
        p.wait()


class Registered(Base):
    def reg(self, **r):
        d = os.path.join(self.cfg.state, "watchers"); os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{r['session']}-{r['job']}-{r['pid']}.json")
        json.dump(r, open(path, "w"))
        return path

    def test_live_dead_and_legacy(self):
        me = os.getpid()
        self.reg(session="alpha", job="111111", pid=me, starttime=starttime(me))
        self.reg(session="beta", job="222222", pid=me, starttime="1")         # reused pid
        self.reg(session="gamma", job="333333", pid=me)                       # no starttime
        live, dead = self.w.registered()
        self.assertEqual(live, {"alpha": {"111111"}})
        self.assertEqual(sorted(r["session"] for r in dead), ["beta", "gamma"])


class Watchers(Base):
    def test_one_shot_mention_is_not_a_watcher(self):
        # Evidence of a poll LOOP is required: a command that merely names the job is not.
        loop = "bash -c while true; do sacct -j 23472564; sleep 300; done"
        once = "bash -c sacct -j 23472564 -X"
        self.assertEqual(self.w.polled_jobs(loop), {"23472564"})
        self.assertEqual(self.w.polled_jobs(once), set())
        self.assertEqual(self.w.polled_jobs("sleep 60"), set())

if __name__ == "__main__":
    unittest.main()
