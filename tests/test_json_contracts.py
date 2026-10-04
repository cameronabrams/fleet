"""A documented `--json` key must be one the tool actually emits.

`fleetwatch --json` and `fleetcontext --json` have in-tree consumers --
`fleetretire` and `fleetboard` -- so their shape is a public interface, and this
repository's versioning rule names "the shape of its `--json`" as part of the
surface a minor bump is decided against. A rule about a shape nobody wrote down
cannot be applied, which is why those shapes are now in the docs.

Documentation of an interface rots the same way a ledger does: it is a second
copy of something derivable, kept by hand. This binds the two together in the one
direction that matters. A key that the docs name and the tool does not emit is a
caller sent to read a field that is not there.

The reverse -- a key emitted and not documented -- is deliberately NOT failed
here. Plenty of fields are incidental, and forcing every one into prose would
make the page a transcript of the dict instead of a description of the contract.
"""
import os
import re
import unittest

from tests.support import APP

# (tool, docs page, the expression in the source that builds the --json payload)
CONTRACTS = [
    ("fleetwatch", "fleetwatch.rst", "json.dumps({"),
    ("fleetcontext", "fleetcontext.rst", "json.dumps({"),
]


def documented_keys(rst_path):
    """Keys named in the ``--json`` section of a docs page.

    Only that section: these pages mention plenty of other literals in backticks,
    and a check that swept the whole file would be asserting against prose."""
    text = open(rst_path).read()
    i = text.find("``--json``\n----------")
    if i < 0:
        return set()
    section = text[i:]
    # ``name`` in a list-table cell, and the run of ``name``s in the prose
    # sentence that lists a row's fields.
    return {m.group(1) for m in re.finditer(r"``([a-z_][a-z0-9_]*)``", section)}


class DocumentedKeysAreEmitted(unittest.TestCase):

    def test_every_documented_key_appears_in_the_tool(self):
        missing = []
        for tool, page, _ in CONTRACTS:
            src = open(os.path.join(APP, "bin", tool)).read()
            rst = os.path.join(APP, "docs", "source", "tools", page)
            for key in sorted(documented_keys(rst)):
                # The docs name the flag itself and a couple of values; a key is
                # anything the tool writes as a dict key or reads as one.
                if key in ("json", "null", "false", "true"):
                    continue
                if f'"{key}"' in src or f"'{key}'" in src:
                    continue
                missing.append(f"{page} documents ``{key}`` but {tool} never names it")
        self.assertEqual(missing, [])

    def test_the_check_is_looking_at_a_real_section(self):
        """A regex that finds nothing passes. If the heading is renamed, this
        test would silently assert over an empty set and report clean -- the
        shape of defect this repository keeps a register of."""
        for tool, page, _ in CONTRACTS:
            keys = documented_keys(os.path.join(APP, "docs", "source", "tools", page))
            self.assertGreater(len(keys), 5,
                               f"{page}: found {len(keys)} documented keys -- the "
                               f"``--json`` section heading has probably moved, and "
                               f"this check is passing by finding nothing")

    def test_the_flag_each_page_documents_is_actually_accepted(self):
        for tool, page, _ in CONTRACTS:
            src = open(os.path.join(APP, "bin", tool)).read()
            self.assertIn("--json", src, f"{page} documents --json; {tool} has no such flag")

    def test_cluster_ok_is_documented_because_skipping_it_is_the_expensive_mistake(self):
        """Not a style point. `fleetwatch` exits 0 when its cluster query fails,
        so a caller that does not read this field concludes there is no work --
        which is what `fleetboard` did until 2026-10-04, drawing an unreachable
        cluster as a calm fleet."""
        rst = open(os.path.join(APP, "docs", "source", "tools", "fleetwatch.rst")).read()
        self.assertIn("cluster_ok", rst)
        i = rst.find("``--json``\n----------")
        self.assertIn("exits 0", rst[i:],
                      "the page must say the command exits 0 on a failed query; "
                      "that is why the field exists")


if __name__ == "__main__":
    unittest.main()
