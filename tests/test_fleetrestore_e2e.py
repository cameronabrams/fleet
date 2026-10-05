"""Build a real fleet on a throwaway tmux server and check where it landed.

This is the test that was missing when `fleetrestore --go` put every session
one pane to the LEFT after the 2026-09-30 reboot: five never started and seven
launched in another session's working directory. Everything else about the tool was
tested; nothing built one and looked.

Three things make it safe to run, and none of them existed before:

- ``--socket``: the fleet is built on a server of this test's own, never the
  caller's. ``fleetrestore`` also clears ``$TMUX`` now, so a run from inside a pane
  cannot reach the surrounding server either.
- a fake ``claude`` earlier on ``PATH``: a ``--go`` restore types
  ``claude --resume`` into panes, so without this the test would launch real
  sessions. The fake records its arguments instead, which is also how the test
  checks that each session was resumed with the right uuid.
- a temporary ``HOME`` holding a ``.tmux.conf``: the bug needed
  ``pane-base-index 1``, and tmux reads that file when the server starts. Using the
  owner's config would make the test pass or fail depending on whose machine it ran
  on.
"""
import json, os, shutil, subprocess, tempfile, time, unittest

from tests.support import APP, BASE_TOML, FakeConfig

TOOL = os.path.join(APP, "bin", "fleetrestore")
SOCKET = "fleet-e2e-test"

FAKE_CLAUDE = """#!/bin/sh
# stands in for claude: records the invocation and exits
echo "$@" >> "$FAKE_CLAUDE_LOG"
"""


def have_tmux():
    return shutil.which("tmux") is not None


@unittest.skipUnless(have_tmux(), "tmux is not installed")
class RestoreLandsWhereTheManifestSays(unittest.TestCase):
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.tmp = tempfile.mkdtemp(prefix="fr-e2e-", dir="/tmp")
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "bin")
        self.sock = os.path.join(self.tmp, "sock")
        for d in (self.home, self.bin, self.sock):
            os.makedirs(d)

        # the setting that broke it. tmux reads this when it starts the server,
        # which is during the restore -- exactly the post-reboot ordering.
        with open(os.path.join(self.home, ".tmux.conf"), "w") as f:
            f.write("set -g base-index 1\nset -g pane-base-index 1\n")

        self.log = os.path.join(self.tmp, "launches")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(fake, 0o755)

        self.dirs = {}
        sessions = []
        for label, win, pane in (("alpha", 2, 0), ("beta", 2, 1), ("gamma", 3, 0)):
            cwd = os.path.join(self.tmp, "cwd-" + label)
            os.makedirs(cwd)
            self.dirs[label] = cwd
            sessions.append({
                "label": label, "cwd": cwd,
                "tmux": {"session": "0", "window": win, "window_name": "w",
                         "pane_index": pane, "pane_id": "%%%d" % (win * 10 + pane),
                         "size": "80x24"},
                "resume_uuid": "u-" + label,
                "resume_uuid_source": "verified: test", "durable_files": []})
        man = {"captured": "now", "installed_claude": "x",
               "coordinator": "coord", "sessions": sessions}
        with open(os.path.join(self.cfg.state, "manifest.json"), "w") as f:
            json.dump(man, f)
        self.man = man

    def tearDown(self):
        self.tmux("kill-server")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.cfg.close()

    def env(self):
        e = dict(os.environ)
        e["HOME"] = self.home
        e["TMUX_TMPDIR"] = self.sock
        e["PATH"] = self.bin + os.pathsep + e.get("PATH", "")
        e["FAKE_CLAUDE_LOG"] = self.log
        e.pop("TMUX", None)
        return e

    def tmux(self, *args):
        return subprocess.run(["tmux", "-L", SOCKET, *args],
                              capture_output=True, text=True, env=self.env())

    def test_every_session_lands_on_its_own_pane_in_its_own_directory(self):
        self.assertNotEqual(self.tmux("has-session", "-t", "0").returncode, 0,
                            "no server should be running: that is the case that broke")

        r = subprocess.run([TOOL, "--go", "--socket", SOCKET, "--stagger", "0"],
                           capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

        # the base index really is 1 here, or the test proves nothing
        base = self.tmux("show-window-options", "-gv", "pane-base-index").stdout.strip()
        self.assertEqual(base, "1", "the test config did not take effect")

        listing = self.tmux("list-panes", "-a", "-F",
                            "#{@agent}\t#{pane_current_path}").stdout
        have = {}
        for line in listing.splitlines():
            label, _, path = line.partition("\t")
            if label:
                have[label] = path
        for s in self.man["sessions"]:
            self.assertIn(s["label"], have,
                          "%s got no pane\n%s" % (s["label"], r.stdout))
            self.assertEqual(os.path.realpath(have[s["label"]]),
                             os.path.realpath(s["cwd"]),
                             "%s landed in the wrong directory" % s["label"])
        self.assertIn("verified:", r.stdout)

    def test_each_session_is_resumed_with_its_own_transcript(self):
        subprocess.run([TOOL, "--go", "--socket", SOCKET, "--stagger", "0"],
                       capture_output=True, text=True, env=self.env())
        for _ in range(50):                      # the shells run it asynchronously
            if os.path.exists(self.log):
                with open(self.log) as fh:
                    if len(fh.readlines()) >= 3:
                        break
            time.sleep(0.1)
        lines = ""
        if os.path.exists(self.log):
            with open(self.log) as fh:
                lines = fh.read()
        for s in self.man["sessions"]:
            self.assertIn("--name %s --resume %s" % (s["label"], s["resume_uuid"]),
                          lines, "wrong or missing launch for %s: %r" % (s["label"], lines))

    def test_it_builds_on_the_named_socket_and_not_the_caller_s(self):
        """`$TMUX` is set inside any pane, so a restore run from one used to build
        the fleet on whatever server that pane belonged to."""
        env = dict(self.env(), TMUX="/some/other/socket,123,0")
        r = subprocess.run([TOOL, "--go", "--socket", SOCKET, "--stagger", "0"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(len(self.tmux("list-panes", "-a").stdout.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(have_tmux(), "tmux is not installed")
class PartialRestoreIntoAnExistingWindow(unittest.TestCase):
    """One session dies; the window it lived in is still there, holding its
    neighbours. Restoring just that session must put it back into THAT window.

    `fleetrestore` templated a window per manifest group and asked only whether
    the tmux SESSION existed, never whether the WINDOW did. So a partial restore
    built a second window and renamed it to the same name, leaving two windows
    called `deps` -- the restored session nowhere near the peers it belongs with.

    Found in the 2026-10-05 restore: 19 of 20 panes came back, and the plan for
    the twentieth was to create a new window and rename it `drexiglas` while a
    four-pane `drexiglas` was already on screen. The coordinator placed that pane
    by hand. Partial restore is the COMMON case -- liveness filtering turns every
    "one session died" into one -- so this is the path most likely to be used.
    """
    def setUp(self):
        self.cfg = FakeConfig(toml=BASE_TOML)
        self.tmp = tempfile.mkdtemp(prefix="fr-part-", dir="/tmp")
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "bin")
        self.sock = os.path.join(self.tmp, "sock")
        for d in (self.home, self.bin, self.sock):
            os.makedirs(d)
        with open(os.path.join(self.home, ".tmux.conf"), "w") as f:
            f.write("set -g base-index 1\nset -g pane-base-index 1\n")
        self.log = os.path.join(self.tmp, "launches")
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(fake, 0o755)

        sessions = []
        # Two windows with DISTINCT names: the defect is about name collision, so
        # a fixture naming every window the same could not show it.
        for label, win, pane, wname in (("alpha", 2, 0, "deps"),
                                        ("beta", 2, 1, "deps"),
                                        ("gamma", 3, 0, "talks")):
            cwd = os.path.join(self.tmp, "cwd-" + label)
            os.makedirs(cwd)
            sessions.append({
                "label": label, "cwd": cwd,
                "tmux": {"session": "0", "window": win, "window_name": wname,
                         "pane_index": pane, "pane_id": "%%%d" % (win * 10 + pane),
                         "size": "80x24"},
                "resume_uuid": "u-" + label,
                "resume_uuid_source": "verified: test", "durable_files": []})
        with open(os.path.join(self.cfg.state, "manifest.json"), "w") as f:
            json.dump({"captured": "now", "installed_claude": "x",
                       "coordinator": "coord", "sessions": sessions}, f)

    def tearDown(self):
        self.tmux("kill-server")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.cfg.close()

    def env(self):
        e = dict(os.environ)
        e["HOME"] = self.home
        e["TMUX_TMPDIR"] = self.sock
        e["PATH"] = self.bin + os.pathsep + e.get("PATH", "")
        e["FAKE_CLAUDE_LOG"] = self.log
        e.pop("TMUX", None)
        return e

    def tmux(self, *args):
        return subprocess.run(["tmux", "-L", SOCKET, *args],
                              capture_output=True, text=True, env=self.env())

    def restore(self, *args):
        return subprocess.run([TOOL, "--go", "--socket", SOCKET, "--stagger", "0",
                               *args], capture_output=True, text=True, env=self.env())

    def windows(self):
        out = self.tmux("list-windows", "-a", "-F", "#{window_name}").stdout
        return [l for l in out.splitlines() if l]

    def panes_in(self, wname):
        out = self.tmux("list-panes", "-a", "-F",
                        "#{window_name}\t#{@agent}").stdout
        return sorted(l.split("\t")[1] for l in out.splitlines()
                      if l.split("\t")[0] == wname and l.split("\t")[1])

    def lose_beta(self):
        """Kill beta's pane, leaving window `deps` alive with alpha in it."""
        out = self.tmux("list-panes", "-a", "-F", "#{@agent}\t#{pane_id}").stdout
        for line in out.splitlines():
            label, _, pid = line.partition("\t")
            if label == "beta":
                self.tmux("kill-pane", "-t", pid)
                return
        self.fail("beta had no pane to kill")

    def test_the_restored_session_rejoins_its_existing_window(self):
        self.assertEqual(self.restore().returncode, 0)
        self.assertEqual(sorted(self.windows()), ["deps", "talks"])
        self.lose_beta()
        self.assertEqual(self.panes_in("deps"), ["alpha"])

        r = self.restore()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(self.windows()), ["deps", "talks"],
                         "a second window was created instead of reusing `deps`"
                         "\n" + r.stdout)
        self.assertEqual(self.panes_in("deps"), ["alpha", "beta"],
                         "beta did not rejoin the window holding its neighbour"
                         "\n" + r.stdout)

    def test_two_windows_of_that_name_is_refused_not_guessed(self):
        """The state this bug used to produce. Picking one would put a session
        beside the wrong neighbours, and both candidates look equally right from
        the manifest -- so the tool stops and names them."""
        self.assertEqual(self.restore().returncode, 0)
        self.lose_beta()
        self.tmux("new-window", "-t", "0:", "-n", "deps")      # a second `deps`
        r = self.restore()
        self.assertIn("2 windows are already named 'deps'", r.stdout)
        self.assertIn("NOT restoring beta", r.stdout)
        self.assertIn("rename or close all but one", r.stdout)
        self.assertEqual(self.panes_in("deps"), ["alpha"],
                         "beta was placed despite the ambiguity")

    def test_the_plan_says_it_will_join_and_creates_nothing(self):
        self.assertEqual(self.restore().returncode, 0)
        self.lose_beta()
        before = sorted(self.windows())
        r = subprocess.run([TOOL, "--socket", SOCKET], capture_output=True,
                           text=True, env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("joins it rather than opening a second window", r.stdout)
        self.assertNotIn("new-window", r.stdout)
        self.assertEqual(sorted(self.windows()), before, "the plan changed tmux")

    def test_a_window_named_claude_is_never_joined(self):
        """`automatic-rename` writes `claude` over any window whose real name was
        lost, so the name identifies nothing. Two unrelated windows can carry it
        at once; joining on it would be a coin toss. The tool already refuses to
        APPLY that name -- it must equally refuse to match on it."""
        src = open(os.path.join(APP, "bin", "fleetrestore")).read()
        self.assertIn('wname != "claude"', src)
        self.tmux("new-session", "-d", "-s", "0", "-n", "claude")
        man = os.path.join(self.cfg.state, "manifest.json")
        with open(man) as f:
            m = json.load(f)
        for s in m["sessions"]:
            s["tmux"]["window_name"] = "claude"
        with open(man, "w") as f:
            json.dump(m, f)
        r = self.restore()
        self.assertNotIn("joins it rather than", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
