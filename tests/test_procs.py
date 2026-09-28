"""Which Claude Code version a binary, a process and the machine carry.

Two install layouts exist. The native installer keeps every version side by
side under `.../versions/<v>/...`, so the path names the version. The npm
install (`npm install -g @anthropic-ai/claude-code`) puts one `claude.exe` under
`node_modules/@anthropic-ai/claude-code/bin/` and upgrades it IN PLACE, so the
path says nothing and only the package.json beside it does.

OBSERVED 2026-09-28 on an npm-installed machine: fleetsnap recorded the
installed claude as `claude` and every session's version as `claude.exe`, and
fleetupgrade's proc_version was None for every session. The "every version
matches" check could not fail.
"""
import json, os, tempfile, unittest
from unittest import mock
from fleet import procs

class BinaryVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def npm_layout(self, version, name="@anthropic-ai/claude-code"):
        pkg = os.path.join(self.tmp.name, "node_modules", "@anthropic-ai", "claude-code")
        os.makedirs(os.path.join(pkg, "bin"))
        with open(os.path.join(pkg, "package.json"), "w") as f:
            json.dump({"name": name, "version": version}, f)
        exe = os.path.join(pkg, "bin", "claude.exe")
        open(exe, "w").close()
        return exe

    def test_native_layout_names_the_version_in_the_path(self):
        self.assertEqual(procs.version_of_binary("/home/u/.local/share/claude/versions/2.1.284"), "2.1.284")
        self.assertEqual(procs.version_of_binary("/home/u/.local/share/claude/versions/2.1.9-beta/claude"), "2.1.9-beta")

    def test_npm_layout_reads_the_package_json(self):
        self.assertEqual(procs.version_of_binary(self.npm_layout("2.1.284")), "2.1.284")

    def test_a_package_json_for_something_else_is_not_a_version(self):
        self.assertIsNone(procs.version_of_binary(self.npm_layout("9.9.9", name="other")))

    def test_a_bare_binary_is_unknown_not_its_basename(self):
        exe = os.path.join(self.tmp.name, "claude.exe")
        open(exe, "w").close()
        self.assertIsNone(procs.version_of_binary(exe))

class ProcessVersion(BinaryVersion):
    def test_reads_the_exe_link(self):
        with mock.patch.object(procs.os, "readlink", return_value=self.npm_layout("2.1.280")):
            self.assertEqual(procs.proc_version(42), "2.1.280")

    def test_a_binary_replaced_in_place_since_launch_is_unknown(self):
        """The package.json now describes the NEW binary; reporting it would make a
        straggler read as already upgraded, which is the one thing fleetupgrade
        must not get wrong."""
        exe = self.npm_layout("2.1.284")
        with mock.patch.object(procs.os, "readlink", return_value=exe + " (deleted)"):
            self.assertIsNone(procs.proc_version(42))

    def test_a_native_path_still_names_the_version_when_deleted(self):
        with mock.patch.object(procs.os, "readlink",
                               return_value="/home/u/.local/share/claude/versions/2.1.270 (deleted)"):
            self.assertEqual(procs.proc_version(42), "2.1.270")

    def test_no_such_process(self):
        with mock.patch.object(procs.os, "readlink", side_effect=OSError):
            self.assertIsNone(procs.proc_version(42))

class InstalledVersion(BinaryVersion):
    def test_from_the_binary_on_path(self):
        exe = self.npm_layout("2.1.284")
        with mock.patch.object(procs.shutil, "which", return_value=exe):
            self.assertEqual(procs.installed_version(), "2.1.284")

    def test_asks_the_binary_when_the_layout_says_nothing(self):
        exe = os.path.join(self.tmp.name, "claude")
        open(exe, "w").close()
        run = mock.Mock(return_value=mock.Mock(stdout="2.1.284 (Claude Code)\n"))
        with mock.patch.object(procs.shutil, "which", return_value=exe), \
             mock.patch.object(procs.subprocess, "run", run):
            self.assertEqual(procs.installed_version(), "2.1.284")
        self.assertEqual(run.call_args[0][0][:2], [exe, "--version"])

    def test_nothing_installed_is_none(self):
        with mock.patch.object(procs.shutil, "which", return_value=None), \
             mock.patch.object(procs.os.path, "exists", return_value=False):
            self.assertIsNone(procs.installed_version())

if __name__ == "__main__":
    unittest.main()
