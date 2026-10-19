"""Finding the fleet's own processes, which stopped working and said nothing.

`claude_procs` identified a session by `basename(argv[0]) == "claude"`. That held
while every session was launched through the installer's symlink, and stopped
holding on 2026-10-17 when this fleet began pinning launches to a release by
path: `argv[0]` became `.../claude/versions/2.1.302`, whose basename is
`2.1.302`.

**Every reader then got an empty list, which is indistinguishable from an idle
fleet.** For two days `fleetcontext` listed no sessions, `fleetnudge` and
`fleetspawn` could find none, and `fleetretire --park drexiglas` answered "no
claude process named 'drexiglas' is running" about a session sitting in a pane.
All 16 were invisible. Nothing failed; four tools just quietly had nothing to
report.

The test that was missing is the one here: launch a REAL process whose `argv[0]`
is a pinned path and ask whether the fleet can see it. Every existing test of the
callers supplied `claude_procs`'s output as a fixture, so the one assumption they
all rested on was the one none of them checked.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from fleet import procs


class _Spawned:
    """A real, live process whose BINARY sits where we choose.

    An earlier version of this set `argv[0]` to a pinned path while the process
    was really `python` -- so `/proc/<pid>/exe` said python, `is_claude` correctly
    said no, and the test failed against the fix. The fixture has to put an actual
    executable at the pinned path, because that is what the real case is: the
    binary IS the release file.

    A script will not do either: for `#!/bin/sh ...`, `/proc/<pid>/exe` is the
    interpreter, not the script.
    """
    def __init__(self, relpath, argv0=None):
        self.dir = tempfile.mkdtemp(prefix="fleet-procs-")
        self.path = os.path.join(self.dir, relpath)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        shutil.copy(shutil.which("sleep") or "/bin/sleep", self.path)
        os.chmod(self.path, 0o755)
        self.argv0 = argv0 or self.path
        self.p = subprocess.Popen([self.argv0, "60"], executable=self.path,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        for _ in range(100):                      # exec has to have happened
            try:
                os.readlink("/proc/%d/exe" % self.p.pid)
                break
            except OSError:
                time.sleep(0.01)

    def __enter__(self):
        return self

    def __exit__(self, *e):
        self.p.kill()
        self.p.wait()
        shutil.rmtree(self.dir, ignore_errors=True)


class ASessionIsFoundHoweverItWasLaunched(unittest.TestCase):
    def test_a_pinned_launch_is_still_a_claude_process(self):
        """The regression, against a live process whose binary really is a file
        in a version store, named by a version number."""
        with _Spawned("claude/versions/2.1.302") as s:
            self.assertTrue(procs.is_claude(s.argv0, s.p.pid))
            self.assertEqual(os.path.basename(s.argv0), "2.1.302",
                             "the basename is what the old check read")

    def test_a_bare_launch_is_still_found(self):
        """`claude` through the installer's symlink: argv[0] alone answers, with
        no syscall at all."""
        with _Spawned("bin/claude", argv0="claude") as s:
            self.assertTrue(procs.is_claude("claude", s.p.pid))
        self.assertTrue(procs.is_claude("/anywhere/bin/claude", 1))

    def test_the_npm_wrapper_name_is_found(self):
        self.assertTrue(procs.is_claude("/n/claude-code/bin/claude.exe", 1))

    def test_an_unrelated_process_is_not(self):
        """The other direction. A false positive is a strange row somebody
        notices; it must still not be routine."""
        with _Spawned("usr/bin/some-daemon") as s:
            self.assertFalse(procs.is_claude(s.argv0, s.p.pid))

    def test_argv_is_consulted_before_proc_and_without_it(self):
        """A session whose `/proc/<pid>/exe` cannot be read -- a permission this
        does not have, or a process exiting mid-scan -- is still found by the old
        route. The two together fail toward FINDING a session, which is the only
        safe direction: a false negative is a fleet that reads as empty."""
        self.assertTrue(procs.is_claude("/x/bin/claude", 2 ** 30))
        self.assertFalse(procs.is_claude("/x/bin/other", 2 ** 30))

    def test_a_binary_replaced_under_a_running_session_is_still_found(self):
        """`/proc/<pid>/exe` grows ` (deleted)` when the file is replaced -- which
        is what an npm upgrade does, in place. The session is still running and
        must not vanish from the fleet because its binary was rewritten
        underneath it.

        The NPM layout is the case that needs the suffix stripped: its basename
        becomes `claude (deleted)`, which matches no name. A native path survives
        either way, because the version regex finds `versions/<v>` anywhere in the
        string -- so a version of this using a native path passed with the strip
        deleted, and proved nothing.
        """
        import unittest.mock as mock
        deleted = "/n/node_modules/@anthropic-ai/claude-code/bin/claude (deleted)"
        with mock.patch.object(procs.os, "readlink", lambda p: deleted):
            self.assertTrue(procs.is_claude("/n/.../claude-code/bin/claude.exe", 1)
                            is True)
            self.assertTrue(procs.is_claude("2.1.300", 1),
                            "an npm binary replaced in place lost its session")

    def test_claude_procs_finds_a_pinned_process_end_to_end(self):
        """Not `is_claude` in isolation: the function the four tools call."""
        with _Spawned("claude/versions/2.1.302") as s:
            found = {p for p, _cwd, _argv in procs.claude_procs()}
            self.assertIn(s.p.pid, found,
                          "a pinned session is invisible to the fleet")


class NoToolIdentifiesAClaudeProcessAlone(unittest.TestCase):
    def test_nothing_in_bin_tests_argv0_for_the_word_claude(self):
        """Exhaustive over `bin/`, because the list-of-three version of this is
        what let the assumption sit in one place and be wrong everywhere."""
        from tests.support import APP
        offenders = []
        for tool in sorted(os.listdir(os.path.join(APP, "bin"))):
            path = os.path.join(APP, "bin", tool)
            if not os.path.isfile(path):
                continue
            try:
                with open(path) as f:
                    src = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(src.splitlines(), 1):
                code = line.split("#")[0]
                if 'basename(argv[0]) == "claude"' in code.replace(" ", " "):
                    offenders.append(f"{tool}:{i}")
                if 'argv[0]) == "claude"' in code:
                    offenders.append(f"{tool}:{i}")
        self.assertEqual(offenders, [], "; ".join(offenders))


if __name__ == "__main__":
    unittest.main()
