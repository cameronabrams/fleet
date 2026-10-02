# Roadmap

Ideas worth doing that have not been done. A living list, not a commitment or a
schedule. When something here is done it moves to `CHANGELOG.md` and comes off
this page.

Rough ordering within each section is by value, not by effort. Items that belong
to the fleet *application* live here; a fleet-level roadmap indexes this file and
carries only what no repository owns.

## Versioning

- **`install` neither records nor reports what it linked.** It symlinks the
  working tree, so the installed version is whatever the checkout is now — which
  is right, and means a machine cannot answer "what did I install, and has it
  moved since?" without looking at git. Worth a line in `install --check`
  rather than a file, since a recorded copy of that is exactly the kind of state
  this repository refuses to keep.

- **`install` ships the conventions as prose and none of the mechanism that makes
  them stick.** It symlinks tools into `~/bin` and skills into `~/.claude/skills`
  and never touches Claude Code's settings file, so a new owner gets
  `examples/conventions.example.md` — pointer-not-payload, the 800-character
  ceiling, the amplification figure — as text, and no hook.

  The general finding behind it, from this fleet's own measurement: a rule that is
  free to follow holds, and a rule with a local cost erodes without feedback *at
  the moment of acting*. The message-size ceiling sat in the conventions file for
  the whole period in which the fleet's mean message size roughly tripled. A line
  in a conventions file is a request competing for attention; a hook is not.
  Shipping the rule as text alone reproduces that drift in every new fleet, by
  construction.

  Two gaps, and they are not equal.

  *The notification hook is the stronger case, and it has an incident behind it.*
  `fleetnudge` falls back to a phone push when it cannot reach a pane, and
  `configuration.rst` says an *existing* notification hook "can then stay the one
  place the topic is written" — it assumes one is already there. A new owner
  following the documentation has none, so that fallback is dead on arrival. The
  sharper form is already documented in `fleetwatch`: with a mute file
  present, an undelivered nudge pushes nothing and the log line is its only trace.
  On 2026-09-17 three nudges failed to reach one session and the push was the
  channel that worked — verifiable in this fleet's nudge log, and the case that
  the delivery section of `fleetwatch` was built from.

  *Message-size feedback was the weaker case, and is no longer.* A `PreToolUse`
  hook on the peer-send tool that logs each send with its length and returns the
  size as context. It should not block: a hard cap makes senders split one thought
  across two messages, and the per-message wrapper is then charged twice, so
  splitting costs more than sending long.

  **2026-10-02, measured across 1,314 peer messages in 8 days: 708 over the
  ceiling, 54%.** Per-session rates ran from 0% to 95%. The hook's own author,
  the coordinator, was the lowest high-volume sender at 20% — and that was not
  discipline. The hook lived in that session's **project** settings, not in
  `~/.claude/settings.json`, so of 1,314 messages it saw 134 and every one was its
  own. Twelve sessions had been writing peer messages with no feedback of any kind
  since the rule existed. The ranking was a ranking of who gets told.

  That is the selection bias this item asked about, and it turned out to be
  mechanical rather than psychological: not "the author knows it is measured" but
  "the instrument was wired to one session." A measurement that samples only its
  own author reports on the author, and nothing in the number says so — the same
  family as `docs/checks-that-reassure.md`.

  The same audit found compliance tracks **recency, not existence**: five days at
  0–2% across 322 messages, immediately after the briefs were written and read,
  then decay to 50–96% as those briefs receded. The rule did not change in that
  window. That is the strongest evidence yet for the general finding above — a
  rule with a local cost erodes without feedback at the moment of acting — and it
  now comes from twelve sessions that did not build the hook.

  Proposed shape: a `hooks/` directory in this repository, and an `install` that
  **offers** to merge them, opt-in, merging and never replacing, with the same
  displaced-file discipline it already uses for symlinks. Opt-in is not timidity —
  that settings file is shared by everything the owner runs with Claude Code, not
  only the fleet.

  **The experiment is now running.** The hook moved to `~/.claude/settings.json`
  on 2026-10-02 and reaches each session at its next restart. What would decide
  it: whether the over-rate falls and *stays* down across sessions that did not
  build it, past the point where this week's telling has receded. The decay curve
  above is what a merely-remembered rule looks like, so anything still holding
  after a quiet fortnight is the hook and not the memory of being told.

  Two confounds to keep in view. Every session was told the rule again on the day
  the hook shipped, so the first days measure both at once; and the sessions were
  told they are being measured, which the 2026-09-13 briefs also did and which
  decayed anyway. Ship the first; the second is now earning its place.

## Measurement

- **Count message-convention compliance on the essential inline part, not the
  whole body.** Requested by the coordinator, 2026-09-22, after the fleet's
  convention was revised to key its ceiling on *cost* rather than *category*:
  inline what the reader must read in full and that is short, everything else a
  pointer. No existing figure counts the way that rule defines, so the headline
  measurement neither convicts nor acquits. Belongs beside `fleetlog`'s initiative
  reconstruction; `fleetcost` is the other candidate home.

  The hard part comes before any code: *essential* is a judgement, not a field,
  and a plausible-looking heuristic that is wrong yields a confident number
  measuring something else — the exact family in `docs/checks-that-reassure.md`.
  Decide the mechanical definition first and state what would falsify it. One
  starting point that classifies rather than guesses: a message carrying a
  pointer is claiming to be one, so its essential part is the ask plus the path,
  and everything beyond that is measurable overage.

  Two things the revision states and nothing counts: the delivery wrapper is
  charged **per message**, so splitting one thought across two costs an extra
  envelope; and framing-versus-substance, where bodies ran about 950 characters
  around roughly 600 of inline-essential content.

  **The 2026-10-02 audit does not close this.** It counts whole bodies against the
  800-character ceiling, which is the count this item says is the wrong one: a
  message that is 1,400 characters of entirely essential content and one that is
  1,400 characters of framing around 300 are the same row in its table. The audit
  is sound for what it measures, and it is the right instrument for whether the
  *ceiling* is obeyed. It is not evidence about whether the **convention** is —
  and the headline figure is quotable enough to be mistaken for both.

## fleetmail

- **Nothing builds the board.** `docs/source/tools/fleetmail.rst` sets out the
  rules a board must be built to — it renders *from* the repository and never
  back into it; it may carry subjects, senders, dates and delivery state; it may
  not carry message bodies or anything named in `[guard] refuse`. The rules are
  the hard half and they are written. Waiting on a second fleet to make it worth
  rendering.

## The screen as a state oracle

- **An unreproduced disagreement between the pane and the session.** Reported
  2026-09-30: `fleetcontext` reported four consecutive times that one pane read
  idle while the session reported busy, and a capture taken by hand seconds later
  showed the busy marker plainly present. `screen_state` checks that marker before
  anything else, so a capture containing it cannot return idle — which means the
  two captures differed, and the one that mattered is gone.

  Not reproduced, and not closed. Ruled out by checking: the pane mapping (the
  tool captures the pane the label says), an empty capture (that returns
  `no-prompt`, not `idle`), a stale marker string (present and matching on
  2.1.285), and width-sensitivity near the auto-compact threshold — the reporter
  raised that one and then lowered it, because only one of the two footers carried
  the `% until auto-compact` text and both produced the disagreement.

  **What the two cases share is a compaction**: one session about to auto-compact,
  one mid-`/compact`. That fits a structural gap rather than a flaky capture.
  `screen_state` can return `trust`, `dialog`, `busy`, `input`, `no-prompt` and
  `idle` — there is **no state for a compacting pane**, and `fleetcontext` learns
  that a compaction happened from the TRANSCRIPT (`compact_boundary`), never from
  the screen. So if a compacting pane draws something other than the busy footer,
  the parse falls through to `idle` while the session correctly reports busy, and
  the two sources disagree by construction for as long as the compaction runs —
  which also explains *sustained but not permanent*, which neither earlier
  candidate did.

  Deliberately not built on yet: nobody has captured a compacting pane, and adding
  a marker for a screen no one has seen would be the same mistake one level down.
  The instrumented line from a run during a compaction confirms or kills it in one
  observation.

  The disagreement now prints the last line the tool itself captured, so the next
  occurrence carries the evidence a later look cannot recover. **What would decide
  it is one recurrence with that line in it.**



- **Nothing checks that the TUI markers still match the installed `claude`.**
  `fleet/panes.py` decides whether a session is busy, at a trust prompt, or holding
  a draft by parsing a captured pane. Two of its markers carry the version they
  were last checked against — and they carry *different* versions, because each was
  re-checked separately after moving. A dim prompt suggestion once read as a
  human's draft in four panes (2026-09-17), which made `fleetnudge` decline to type
  into sessions that were in fact idle.

  `reconcile()` now covers the busy/idle half: `claude agents` answers that
  structurally, so a moved busy marker is caught and named rather than acting as a
  silent refusal. **The other states have no second source.** `trust`, `dialog` and
  `input` are visible only on the screen, so if one of those markers moves there is
  nothing to disagree with it — and every one of them fails toward *decline*, which
  is the reassuring direction: the tool goes quiet and the fleet looks calm.

  What would decide it: whether a marker check can be made to fail loudly on its
  own. The candidates are a canary — capture a pane in a known state at a known
  version and assert the parse — or recording the version each marker was last
  confirmed against and warning when the installed binary has moved past it. The
  second is cheap and catches the class; it does not prove the marker is still
  right, only that nobody has looked since it changed.

## Visibility

- **`fleetwatch` could check that tmux's lock is real.** It reports who is
  attached; the operational control beside that is tmux's own `lock-after-time`
  with a `lock-command`. A `lock-command` naming a binary that is not installed
  fails toward *unlocked* and looks configured, which is this repository's
  signature failure. Both facts are derivable — `tmux show-options -g` and a
  `PATH` lookup — so the check is small. The judgement is whether a tool about
  fleet state should comment on the host's configuration at all.
