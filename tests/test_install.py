"""`install`, on the machine it exists for: one that has nothing yet.

The fresh-machine path is the whole point of this script, and it is the path
least likely to be exercised by the person who maintains it -- their machine has
had a fleet on it for months. Walked end to end on 2026-10-21 and it was wrong in
two ways at once (see `test_the_skills_directory_is_created` and
`test_a_failed_link_is_not_reported_as_a_successful_install`).

Nothing here touches the real HOME, the real configuration or the real ~/bin.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.support import APP, BASE_TOML


class FreshMachine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-install-")
        self.home = os.path.join(self._tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def configure(self):
        d = os.path.join(self.home, ".config", "fleet")
        os.makedirs(d, exist_ok=True)
        state = os.path.join(self._tmp.name, "state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(d, "fleet.toml"), "w") as f:
            f.write(BASE_TOML.format(state=state))
        return d

    def install(self, *args):
        env = dict(os.environ, HOME=self.home)
        env.pop("FLEET_CONFIG", None)
        return subprocess.run([os.path.join(APP, "install"), *args],
                              capture_output=True, text=True, env=env, cwd=APP,
                              timeout=60)

    # -- the blocker ----------------------------------------------------------

    def test_no_configuration_refuses_with_exit_2(self):
        """Nothing else can run without a fleet.toml, so this is the step that
        blocks every other step -- and it must say so in a status a caller can
        branch on, not only in prose."""
        r = self.install()
        self.assertEqual(r.returncode, 2)
        self.assertIn("fleetinit", r.stdout)

    def test_the_refusal_names_the_command_not_the_file(self):
        """Naming a file to copy leaves a human editing TOML by hand, which is
        the step `fleetinit` exists to remove."""
        r = self.install()
        self.assertIn("fleetinit --go", r.stdout)
        self.assertIn("--from", r.stdout)

    # -- what a successful install actually does ------------------------------

    def test_the_tools_are_linked(self):
        self.configure()
        r = self.install("--go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        linked = os.listdir(os.path.join(self.home, "bin"))
        for tool in ("fleetboard", "fleetsnap", "fleetinit"):
            self.assertIn(tool, linked)
        self.assertTrue(os.path.islink(os.path.join(self.home, "bin", "fleetboard")))

    def test_the_skills_directory_is_created(self):
        """THE FRESH-MACHINE BUG. `~/.claude/skills` does not exist on a machine
        where Claude Code has never written a skill -- precisely the machine this
        script is for -- and `install` created `~/bin` but not this one. Every
        skill link failed with `No such file or directory`."""
        self.configure()
        r = self.install("--go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        skills = os.path.join(self.home, ".claude", "skills")
        self.assertTrue(os.path.isdir(skills), "install must create the skills dir")
        shipped = [d for d in os.listdir(os.path.join(APP, "skills"))
                   if os.path.isdir(os.path.join(APP, "skills", d))]
        self.assertTrue(shipped, "the repository ships no skills to link")
        for s in shipped:
            self.assertTrue(os.path.islink(os.path.join(skills, s)), s)

    def test_a_failed_link_is_not_reported_as_a_successful_install(self):
        """THE SECOND HALF, and the worse one. Those six failures printed
        `ln: ... No such file or directory` and the script still exited 0 -- errors
        on screen and success to anything reading the status. An installer may be
        wrong in many directions; this is the one it may not be wrong in.

        Forced by making `~/.claude` a FILE, so the directory cannot be created
        and the links beneath it cannot be made."""
        self.configure()
        os.makedirs(self.home, exist_ok=True)
        with open(os.path.join(self.home, ".claude"), "w") as f:
            f.write("not a directory\n")
        r = self.install("--go")
        self.assertNotEqual(r.returncode, 0,
                            "a link that could not be made must fail the install")
        self.assertIn("FAILED", r.stdout)
        self.assertIn("INCOMPLETE", r.stdout)

    # -- read-only by default -------------------------------------------------

    def test_without_go_nothing_is_created(self):
        """Read-only by default, like every other tool here."""
        self.configure()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.home, "bin")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))
        self.assertIn("plan only", r.stdout)

    def test_a_second_install_is_a_no_op_not_a_replacement(self):
        """Re-running must not displace the links it made last time: `install` is
        run again after every `git pull`, and a REPLACE on each one would fill
        the displaced-originals directory with its own symlinks."""
        self.configure()
        self.install("--go")
        r = self.install("--go")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("REPLACE", r.stdout)
        self.assertIn("ok", r.stdout)
