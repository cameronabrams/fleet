"""The version, and the release notes built from it.

A version bumped in one place and not the other is the failure that looks like
nothing at all: everything imports, every test passes, and the docs and the tag
quietly disagree about what you are running. So the two are tied together here.
"""
import os, re, subprocess, sys, unittest

import fleet
from tests.support import APP

CHANGELOG = os.path.join(APP, "CHANGELOG.md")
sys.path.insert(0, os.path.join(APP, "scripts"))
from changelog_notes import notes


def released_versions():
    """Every `## [x.y.z] - date` heading, newest first, as written."""
    with open(CHANGELOG) as f:
        return re.findall(r"^## \[(\d+\.\d+\.\d+[^\]]*)\] - (\d{4}-\d{2}-\d{2})\s*$",
                          f.read(), re.M)


class Version(unittest.TestCase):
    def test_version_is_a_semantic_version(self):
        self.assertRegex(fleet.__version__, r"^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$")

    def test_it_matches_the_newest_released_entry(self):
        """Before the first release there is no entry to match, and __version__
        must say so rather than naming a version nobody can check out."""
        rel = released_versions()
        if not rel:
            self.assertEqual(fleet.__version__, "0.0.0",
                             "no released entry in CHANGELOG.md, so __version__ "
                             "must still be the unreleased 0.0.0")
            return
        self.assertEqual(fleet.__version__, rel[0][0],
                         "fleet.__version__ and the newest CHANGELOG entry disagree; "
                         "scripts/release.sh writes both, so one was edited by hand")

    def test_the_changelog_still_has_an_unreleased_section(self):
        with open(CHANGELOG) as f:
            self.assertIn("## [Unreleased]", f.read(),
                          "release.sh needs it, and without it the next release "
                          "has nowhere to put its notes")

    def test_docs_take_the_version_from_the_one_place_it_is_written(self):
        conf = os.path.join(APP, "docs", "source", "conf.py")
        with open(conf) as f:
            text = f.read()
        self.assertIn("fleet.__version__", text)
        self.assertNotRegex(text, r"^release\s*=\s*['\"]\d",
                            "a literal version in conf.py is a second copy that rots")


class ChangelogNotes(unittest.TestCase):
    SAMPLE = (
        "# Changelog\n\npreamble\n\n"
        "## [Unreleased]\n\n"
        "## [0.2.0] - 2026-10-01\n\n### Added\n- a thing\n\n"
        "## [0.1.0] - 2026-09-23\n\n### Fixed\n- an older thing\n\n"
        "[0.2.0]: https://example.invalid/v0.2.0\n"
        "[0.1.0]: https://example.invalid/v0.1.0\n")

    def test_extracts_one_section_and_stops_at_the_next(self):
        self.assertEqual(notes(self.SAMPLE, "0.2.0"), "### Added\n- a thing")

    def test_the_last_section_does_not_swallow_the_link_footer(self):
        # Link references are not headings, so a naive "read to the next ## or EOF"
        # appends them to the oldest release's notes.
        self.assertEqual(notes(self.SAMPLE, "0.1.0"), "### Fixed\n- an older thing")

    def test_an_empty_section_is_empty_not_missing(self):
        self.assertEqual(notes(self.SAMPLE, "Unreleased"), "")

    def test_an_unknown_version_is_none(self):
        self.assertIsNone(notes(self.SAMPLE, "9.9.9"))

    def test_the_script_refuses_rather_than_printing_nothing(self):
        """An empty extraction would become a release body with no notes, which
        reads as a release that changed nothing rather than a broken script."""
        script = os.path.join(APP, "scripts", "changelog_notes.py")
        r = subprocess.run([sys.executable, script, "9.9.9", CHANGELOG],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("no section", r.stderr)

    def test_the_real_changelog_has_notes_for_whatever_comes_next(self):
        """Whichever section the next release will publish must be non-empty --
        the released one if there is one, otherwise [Unreleased]."""
        rel = released_versions()
        which = rel[0][0] if rel else "Unreleased"
        r = subprocess.run([sys.executable,
                            os.path.join(APP, "scripts", "changelog_notes.py"),
                            which, CHANGELOG], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
