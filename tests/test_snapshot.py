"""Whether the pending-updates document still describes this machine.

`fleetboard` printed `updates: 47 updates -> 20261021` for nearly seven hours
after Cameron had installed those 47 updates. The age beside it was honest; the
count was about a machine that no longer existed. He suggested an install should
reset the flag -- which means hooking the package manager. It does not: the
machine already says which snapshot it is on and the document already says which
one it was aiming at.
"""
import os
import tempfile
import unittest

from fleet import snapshot


class ReadingTheId(unittest.TestCase):
    def write(self, text):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: None)
        p = os.path.join(d, "os-release")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_a_quoted_id(self):
        self.assertEqual(snapshot.current(self.write('VERSION_ID="20261021"\n')),
                         "20261021")

    def test_an_unquoted_id(self):
        """os-release permits both, and a reader that honored the quotes would
        compare `"20261021"` against `20261021` and call them different."""
        self.assertEqual(snapshot.current(self.write("VERSION_ID=20261021\n")),
                         "20261021")

    def test_other_keys_are_ignored(self):
        p = self.write('NAME="openSUSE"\nVERSION_ID="15.5"\nID_LIKE=suse\n')
        self.assertEqual(snapshot.current(p), "15.5")

    def test_a_missing_file_is_none(self):
        self.assertIsNone(snapshot.current("/no/such/os-release"))

    def test_a_file_without_the_key_is_none(self):
        self.assertIsNone(snapshot.current(self.write('NAME="x"\n')))

    def test_an_empty_value_is_none_not_empty_string(self):
        self.assertIsNone(snapshot.current(self.write('VERSION_ID=""\n')))


class HasTheDocumentBeenOvertaken(unittest.TestCase):
    DOC = {"snapshot": "20261020", "target_snapshot": "20261021", "total": 47}

    def test_reaching_the_documents_own_target_is_supersession(self):
        self.assertIs(snapshot.superseded(self.DOC, now_id="20261021"), True)

    def test_still_on_the_recorded_snapshot_is_not(self):
        self.assertIs(snapshot.superseded(self.DOC, now_id="20261020"), False)

    def test_a_third_snapshot_is_not_supersession_of_THIS_document(self):
        """The machine moved, but not to the target this document named, so this
        document's count is not provably spent. Reported as still current rather
        than guessed at -- the board then shows the count with its age, which is
        what it did before and is never wrong, only incomplete."""
        self.assertIs(snapshot.superseded(self.DOC, now_id="20261019"), False)

    def test_a_distribution_whose_id_is_not_a_snapshot_never_cries_wolf(self):
        """THE reason the rule is "reached the stated target" and not "the ids
        differ". On a release distribution `VERSION_ID` is something like `15.5`
        while a producer may record a date, so they would differ permanently and
        the board would report supersession for ever."""
        doc = {"snapshot": "20261020", "target_snapshot": "20261021"}
        self.assertIs(snapshot.superseded(doc, now_id="15.5"), False)

    def test_nothing_pending_cannot_be_superseded(self):
        """The document's target IS where the machine already was, so reaching it
        proves nothing about whether the check has re-run."""
        doc = {"snapshot": "20261021", "target_snapshot": "20261021", "total": 0}
        self.assertIs(snapshot.superseded(doc, now_id="20261021"), False)


class UnknownIsNotFine(unittest.TestCase):
    """None means it cannot be told, and the caller must then report what it
    reported before rather than guessing in either direction."""

    def test_an_unreadable_os_release(self):
        doc = {"snapshot": "a", "target_snapshot": "b"}
        self.assertIsNone(snapshot.superseded(doc, path="/no/such/file"))

    def test_a_document_with_no_target(self):
        self.assertIsNone(snapshot.superseded({"snapshot": "a"}, now_id="b"))

    def test_a_document_with_no_snapshot(self):
        self.assertIsNone(snapshot.superseded({"target_snapshot": "b"}, now_id="b"))

    def test_something_that_is_not_a_document(self):
        self.assertIsNone(snapshot.superseded(None, now_id="b"))
        self.assertIsNone(snapshot.superseded("not a dict", now_id="b"))

    def test_numbers_compare_as_strings(self):
        """A producer writing ints and an os-release giving a string must still
        agree; comparing them raw would make 20261021 != '20261021'."""
        doc = {"snapshot": 20261020, "target_snapshot": 20261021}
        self.assertIs(snapshot.superseded(doc, now_id="20261021"), True)
