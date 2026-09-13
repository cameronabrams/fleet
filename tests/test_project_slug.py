"""A working directory -> Claude Code's project-directory name.

Claude Code maps every character other than [A-Za-z0-9] to '-'. The tools used
to map only '/', which is identical for most paths and wrong for any with a dot:
OBSERVED 2026-09-13, cwd ~/.local/state/fleet lives in
~/.claude/projects/-home-<user>--local-state-fleet, and fleetupgrade could not
resolve that session's uuid at all.
"""
import os, tempfile, unittest
from unittest import mock
from tests.support import FakeConfig, load_tool
from fleet import transcripts

DOTTED = "/home/u/.local/state/fleet"
DOTTED_SLUG = "-home-u--local-state-fleet"
UUID = "aaaaaaaa-0000-4000-8000-000000000001"

class ProjectSlug(unittest.TestCase):
    def test_plain_path(self):
        self.assertEqual(transcripts.project_slug("/home/u/Git/fleet"), "-home-u-Git-fleet")

    def test_dot_becomes_dash(self):
        self.assertEqual(transcripts.project_slug(DOTTED), DOTTED_SLUG)

    def test_observed_scratchpad_project(self):
        # the shape of a real scratchpad project dir: a slash-dash becomes "--"
        self.assertEqual(
            transcripts.project_slug("/tmp/claude-1000/-home-u/abcdef01-2345-4678-9abc-def012345678/scratchpad"),
            "-tmp-claude-1000--home-u-abcdef01-2345-4678-9abc-def012345678-scratchpad")


class ToolsUseIt(unittest.TestCase):
    """Each tool that locates a project directory, on a dotted cwd."""
    def setUp(self):
        self.cfg = FakeConfig()
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = os.path.join(self.tmp.name, "projects")
        self.scratch = os.path.join(self.tmp.name, "scratch")
        os.makedirs(os.path.join(self.projects, DOTTED_SLUG))
        os.makedirs(os.path.join(self.scratch, DOTTED_SLUG, UUID))
        with open(os.path.join(self.projects, DOTTED_SLUG, UUID + ".jsonl"), "w") as f:
            f.write('{"type":"agent-name","agentName":"coord"}\n')

    def tearDown(self):
        self.tmp.cleanup(); self.cfg.close()

    def test_fleetupgrade_finds_scratchpad_uuid(self):
        up = load_tool("fleetupgrade")
        with mock.patch.object(up, "SCRATCH", self.scratch), \
             mock.patch.object(up, "PROJECTS", self.projects):
            self.assertEqual(up.live_uuids(DOTTED, 3), [UUID])
            self.assertEqual(up.name_from_transcript(DOTTED, UUID), "coord")

    def test_fleetsnap_finds_transcript(self):
        snap = load_tool("fleetsnap")
        with mock.patch.object(snap, "PROJECTS", self.projects):
            uuid, how = snap.newest_transcript(DOTTED, "coord")
        self.assertEqual(uuid, UUID)
        self.assertTrue(how.startswith("verified"), how)

if __name__ == "__main__":
    unittest.main()
