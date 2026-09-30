"""Build a real fleet on a throwaway tmux server and check where it landed.

This is the test that was missing when `fleetrestore --all --go` put every session
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
                "label": label, "fleet": "f", "cwd": cwd,
                "tmux": {"session": "0", "window": win, "window_name": "f",
                         "pane_index": pane, "pane_id": "%%%d" % (win * 10 + pane),
                         "size": "80x24"},
                "resume_uuid": "u-" + label,
                "resume_uuid_source": "verified: test", "durable_files": []})
        man = {"captured": "now", "installed_claude": "x", "fleet": "f",
               "coordinator": "coord", "sessions": sessions}
        for name in ("manifest", "f"):
            with open(os.path.join(self.cfg.state, name + ".json"), "w") as f:
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

        r = subprocess.run([TOOL, "--all", "--go", "--socket", SOCKET, "--stagger", "0"],
                           capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

        # the base index really is 1 here, or the test proves nothing
        base = self.tmux("show-window-options", "-gv", "pane-base-index").stdout.strip()
        self.assertEqual(base, "1", "the test config did not take effect")

        listing = self.tmux("list-panes", "-a", "-F",
                            "#{@repo}\t#{pane_current_path}").stdout
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
        subprocess.run([TOOL, "--all", "--go", "--socket", SOCKET, "--stagger", "0"],
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
        r = subprocess.run([TOOL, "--all", "--go", "--socket", SOCKET, "--stagger", "0"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(len(self.tmux("list-panes", "-a").stdout.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
