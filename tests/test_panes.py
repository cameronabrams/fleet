import unittest
from unittest import mock
from fleet import panes

RULE = "─" * 30
D, R = "\x1b[2m", "\x1b[0m"

def box(line, footer="  footer"):
    return f"⏺ done\n{RULE}\n{line}\n{RULE}\n{footer}\n"


class Suggestions(unittest.TestCase):
    # Lines as `capture-pane -p -e` showed them on 2026-09-17.
    WORDS = f"\x1b[39m❯\xa0{D}go{R} {D}ahead{R} {D}with{R} {D}the{R} {D}test{R}"
    RUN = f"\x1b[39m❯\xa0{D}commit and push main.tex{R}"
    EMPTY_BUSY = "\x1b[38;5;246m❯\xa0\x1b[39m"
    TYPED = "\x1b[38;5;246m❯\xa0\x1b[39mzq"

    def test_a_dim_suggestion_is_not_a_draft(self):
        for line in (self.WORDS, self.RUN):
            self.assertEqual(panes.input_line(box(line)), "")
            self.assertEqual(panes.screen_state(box(line)), "idle")

    def test_typed_text_is_a_draft(self):
        self.assertEqual(panes.input_line(box(self.TYPED)), "zq")
        self.assertEqual(panes.screen_state(box(self.TYPED)), "input")
        self.assertEqual(panes.input_line(box(self.EMPTY_BUSY)), "")

    def test_typed_text_with_a_dim_completion_after_it(self):
        self.assertEqual(panes.input_line(box(f"\x1b[39m❯\xa0/comp{D}act{R}")), "/comp")

    def test_dim_ends_at_22_and_survives_colour_changes(self):
        self.assertEqual(panes.undimmed(f"a{D}b\x1b[22mc"), "ac")
        self.assertEqual(panes.undimmed(f"a{D}b\x1b[38;5;2mc{R}d"), "ad")      # colour changes keep dim
        self.assertEqual(panes.undimmed("a\x1b[38;5;2mb"), "ab")                # 38;5;2 is colour 2, not dim
        self.assertEqual(panes.undimmed("a\x1b[38;2;2;2;2mb\x1b[48;5;2mc"), "abc")
        self.assertEqual(panes.undimmed(f"a\x1b[1mb\x1b[mc"), "abc")            # bold is not dim
        self.assertEqual(panes.undimmed(f"a{D}b\x1b[mc"), "ac")                  # bare reset

    def test_a_wrapped_suggestion_is_not_a_draft(self):
        scr = f"{RULE}\n\x1b[39m❯\xa0{D}go ahead with the{R}\n  {D}cache fill{R}\n{RULE}\n"
        self.assertEqual(panes.input_line(scr), "")

    def test_markers_are_found_through_escapes(self):
        split = box(self.EMPTY_BUSY, footer="  esc\x1b[39m to interrupt")
        self.assertEqual(panes.screen_state(split), "busy")
        trust = "Is this a \x1b[1mproject\x1b[0m you created or one you trust?"
        self.assertEqual(panes.screen_state(trust), "trust")
        dialog = "Background\x1b[0m work is running"
        self.assertEqual(panes.screen_state(dialog), "dialog")

    def test_echoed_history_prompt_is_not_the_input_line(self):
        scr = f"\x1b[38;5;246m❯\x1b[39m status report\n⏺ ok\n{RULE}\n{self.RUN}\n{RULE}\n"
        self.assertEqual(panes.input_line(scr), "")


class TypeLine(unittest.TestCase):
    def run_type(self, echo):
        calls = []
        def tmux(*a):
            calls.append(a)
            if a[0] == "capture-pane":
                self.assertIn("-e", a)                   # attributes must be captured
                return 0, box(echo), ""
            return 0, "", ""
        with mock.patch.object(panes.time, "sleep"), \
             mock.patch.object(panes.time, "time", side_effect=iter(range(100)).__next__):
            return panes.type_line(tmux, "%1", "/color red"), calls

    def test_reads_back_through_a_dim_ghost(self):
        err, calls = self.run_type(f"\x1b[39m❯\xa0/color red{D} (current: blue){R}")
        self.assertIsNone(err)
        self.assertNotIn(("send-keys", "-t", "%1", "C-u"), calls)

    def test_a_trailing_semicolon_goes_as_a_key_code(self):
        calls = []
        panes.send_text(lambda *a: calls.append(a) or (0, "", ""), "%1", "all 8 tasks: COMPLETED;;")
        self.assertEqual(calls, [("send-keys", "-t", "%1", "-l", "all 8 tasks: COMPLETED"),
                                 ("send-keys", "-t", "%1", "-H", "3b"),
                                 ("send-keys", "-t", "%1", "-H", "3b")])
        calls.clear()
        panes.send_text(lambda *a: calls.append(a) or (0, "", ""), "%1", "mid;dle")
        self.assertEqual(calls, [("send-keys", "-t", "%1", "-l", "mid;dle")])

    def test_readback_survives_a_mid_word_wrap(self):
        err, _ = self.run_type("\x1b[39m❯\xa0/color re\n  d")     # wrapped mid-word
        self.assertIsNone(err)

    def test_clearing_falls_back_to_backspaces(self):
        held = ["still here", ""]
        calls = []
        def tmux(*a):
            calls.append(a)
            if a[0] == "capture-pane":
                return 0, box(f"\x1b[39m❯\xa0{held[0]}"), ""
            if a[-1] == "BSpace":
                held[0] = held.pop(1) if len(held) > 1 else ""
            return 0, "", ""
        with mock.patch.object(panes.time, "sleep"):
            self.assertTrue(panes.clear_input(tmux, "%1"))
        self.assertIn(("send-keys", "-t", "%1", "C-u"), calls)
        self.assertIn(("send-keys", "-t", "%1", "-N", "60", "BSpace"), calls)

    def test_input_that_will_not_clear_is_reported(self):
        def tmux(*a):
            if a[0] == "capture-pane":
                return 0, box("\x1b[39m❯\xa0stuck"), ""
            return 0, "", ""
        with mock.patch.object(panes.time, "sleep"):
            self.assertFalse(panes.clear_input(tmux, "%1"))
            err = panes.type_line(tmux, "%1", "/color red", wait=0)
        self.assertIn("COULD NOT BE CLEARED", err)

    def test_a_suggestion_left_in_place_is_not_a_readback(self):
        err, calls = self.run_type(f"\x1b[39m❯\xa0{D}/color red{R}")
        self.assertIsNotNone(err)
        self.assertIn(("send-keys", "-t", "%1", "C-u"), calls)


class InFleet(unittest.TestCase):
    """`tmux list-panes -a` crosses tmux SESSIONS. On 2026-09-26 that put one of
    the human's own windows into fleetupgrade's count and produced a restart plan
    for it with CCP_AGENT=1 prepended -- the flag that makes a session an
    addressable agent. The plan asserted an environment it never observed."""

    def test_either_label_is_enough_and_neither_is_not(self):
        self.assertTrue(panes.in_fleet("coord", "coord"))
        self.assertTrue(panes.in_fleet("coord", ""))        # relabelled by hand
        self.assertTrue(panes.in_fleet("", "records"))
        self.assertFalse(panes.in_fleet("", ""))
        self.assertFalse(panes.in_fleet(None, None))        # tmux gives "" not None

    def test_whitespace_is_not_a_label(self):
        self.assertFalse(panes.in_fleet("  ", "\t"))


if __name__ == "__main__":
    unittest.main()
