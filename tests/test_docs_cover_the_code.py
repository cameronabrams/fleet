"""Every module and every tool has a page, and every page is reachable.

Written because the gap sat open for weeks and was noticed only by looking:
`docs/source/api/` had pages for three of nine `fleet/` modules, and a module
added during this session made it four of ten. Nothing failed -- Sphinx builds a
documentation set that silently omits whatever nobody listed, so the only signal
was somebody going and counting.

These are exhaustive over the directories rather than lists of names. A list is
what let the omission happen: whoever adds the tenth module is not on it.
"""
import os
import re
import unittest

from tests.support import APP

API = os.path.join(APP, "docs", "source", "api")
TOOLDOCS = os.path.join(APP, "docs", "source", "tools")


def modules():
    return sorted(f[:-3] for f in os.listdir(os.path.join(APP, "fleet"))
                  if f.endswith(".py") and f != "__init__.py")


def tools():
    out = []
    for f in sorted(os.listdir(os.path.join(APP, "bin"))):
        p = os.path.join(APP, "bin", f)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            out.append(f)
    return out


class EveryModuleIsDocumented(unittest.TestCase):
    def test_each_has_a_page(self):
        missing = [m for m in modules()
                   if not os.path.isfile(os.path.join(API, "fleet.%s.rst" % m))]
        self.assertEqual(missing, [], "no API page for: " + ", ".join(missing))

    def test_each_page_is_in_the_package_toctree(self):
        """A page nobody links is a page Sphinx builds and nobody reaches."""
        with open(os.path.join(API, "fleet.rst")) as f:
            listed = {l.strip() for l in f}
        missing = [m for m in modules() if "fleet.%s" % m not in listed]
        self.assertEqual(missing, [], "not in the toctree: " + ", ".join(missing))

    def test_no_page_names_a_module_that_is_gone(self):
        """The other direction: a page for a deleted module builds an empty
        section rather than failing."""
        have = set(modules())
        stale = []
        for f in os.listdir(API):
            m = re.fullmatch(r"fleet\.([a-z_]+)\.rst", f)
            if m and m.group(1) not in have:
                stale.append(f)
        self.assertEqual(stale, [], "pages for modules that no longer exist: "
                                    + ", ".join(stale))


class EveryToolIsDocumented(unittest.TestCase):
    def test_each_has_a_page(self):
        missing = [t for t in tools()
                   if not os.path.isfile(os.path.join(TOOLDOCS, "%s.rst" % t))]
        self.assertEqual(missing, [], "no page for: " + ", ".join(missing))

    def test_each_is_in_the_tools_toctree(self):
        with open(os.path.join(TOOLDOCS, "index.rst")) as f:
            listed = {l.strip() for l in f}
        missing = [t for t in tools() if t not in listed]
        self.assertEqual(missing, [], "not in the toctree: " + ", ".join(missing))

    def test_each_is_in_the_summary_table(self):
        """The table is what a reader scans first; a tool absent from it is a
        tool nobody finds, page or no page."""
        with open(os.path.join(TOOLDOCS, "index.rst")) as f:
            text = f.read()
        missing = [t for t in tools() if ":doc:`%s`" % t not in text]
        self.assertEqual(missing, [], "not in the summary table: " + ", ".join(missing))


class EverySectionOfTheConfigurationIsDocumented(unittest.TestCase):
    """`fleet.toml` grew `[fleet]` and `[updates]` this week and neither reached
    the configuration page until somebody asked whether the docs were updated."""
    def test_each_section_the_example_declares_has_a_heading(self):
        with open(os.path.join(APP, "examples", "fleet.example.toml")) as f:
            example = f.read()
        with open(os.path.join(APP, "docs", "source", "configuration.rst")) as f:
            doc = f.read()
        sections = {m.split(".")[0] for m in
                    re.findall(r"^\[\[?([^\]]+)\]\]?", example, re.M)}
        missing = sorted(s for s in sections
                         if "``[%s]``" % s not in doc
                         and "``[%s.<name>]``" % s not in doc)
        self.assertEqual(missing, [],
                         "declared in the example, undocumented: " + ", ".join(missing))
