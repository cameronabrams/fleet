"""Reading a Claude Code pane, and typing one line into it safely.

Shared by fleetcontext and fleetnudge, so "is this pane idle" and "did the typed
line arrive intact" have one answer. Nothing here calls tmux itself: the caller
passes its own `tmux` function, which is what the tools' tests replace.
"""
import re
import time

BUSY_MARKER = "esc to interrupt"           # footer while a turn runs (2.1.270)
TRUST_MARKERS = ("trust this folder", "Is this a project you created")
BACKGROUND_MARKER = "Background work is running"
PROMPT = "❯"                              # the input line, followed by a no-break space when empty (2.1.272)
RULE = re.compile(r"^\s*─{3,}")           # the rules drawn above and below the input line
TYPE_WAIT = 5.0                            # seconds for typed text to reach the input line

def input_line(text):
    """What the input line holds, whitespace-collapsed ("" when empty), or None if
    no input line is drawn. The input line is a PROMPT line followed, after any
    wrapped continuation, by a rule; earlier prompt lines on screen are history,
    so the last such line wins."""
    lines, found = text.splitlines(), None
    for i, line in enumerate(lines):
        if not re.match(r"^\s*" + PROMPT, line):
            continue
        j = i + 1
        while j < len(lines) and not RULE.match(lines[j]):
            j += 1
        if j < len(lines):
            found = " ".join([line.split(PROMPT, 1)[1]] + lines[i + 1:j])
    return None if found is None else " ".join(found.split())

def screen_state(text):
    """idle, busy, trust, dialog, input (text already typed) or no-prompt."""
    if any(m in text for m in TRUST_MARKERS):
        return "trust"
    if BACKGROUND_MARKER in text:
        return "dialog"
    if BUSY_MARKER in text:
        return "busy"
    held = input_line(text)
    if held is None:
        return "no-prompt"
    return "input" if held else "idle"

def state_problem(state, name, pane):
    """Why a pane in `state` must not be typed into, or None when it is idle."""
    return {
        "trust": f"pane {pane} shows the folder-trust prompt",
        "dialog": f"pane {pane} shows the background-work dialog",
        "busy": f"{name} is mid-turn; wait until it is idle",
        "input": (f"the input line in {pane} already holds text (a draft, or a dialog); "
                  f"typing would add to it"),
        "no-prompt": f"pane {pane} shows no input line (a dialog or a menu?)",
        "no-pane": "no tmux pane shows this session",
    }.get(state)

def type_line(tmux, pane, line, wait=TYPE_WAIT):
    """Type `line` without Enter and confirm the input line holds exactly it.
    Returns None, or the reason it did not (the input line is then cleared)."""
    tmux("send-keys", "-t", pane, "-l", line)
    want = " ".join(line.split())
    t_end = time.time() + wait
    while time.time() < t_end:
        time.sleep(0.5)
        if input_line(tmux("capture-pane", "-p", "-t", pane)[1]) == want:
            return None
    tmux("send-keys", "-t", pane, "C-u")
    return (f"the input line in {pane} did not read exactly {line!r} within {wait:.0f}s "
            f"(a terminal reply can corrupt keys); cleared it and stopped")
