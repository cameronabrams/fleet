# Roadmap

Ideas worth doing that have not been done. A living list, not a commitment or a
schedule. When something here is done it moves to `CHANGELOG.md` and comes off
this page.

Rough ordering within each section is by value, not by effort. Items that belong
to the fleet *application* live here; a fleet-level roadmap indexes this file and
carries only what no repository owns.

## Identity and attribution

- **`fleetlog` can still state a rename it cannot know about.** `v0.1.0` fixed
  this for `fleetgantt` by gating the rename branch on the transcript's own name
  record (`own_seq`), because the rename table is keyed by bare name across every
  transcript and auto-generated display names are not unique. `fleetlog` calls
  `identity.attribute` without `own_seq`, deliberately: the message graph wants
  old messages under the role that sent them, and a graph has no lane to
  mislabel. But it still prints a `how`, and that `how` can say "renamed" on the
  same evidence that was wrong in the chart.

  What would decide it: whether any `fleetlog` output is read as an identity
  rather than as an edge. If it is, the gate applies there too; if not, the
  docstring should say so where the caller can see it, not only where the
  function is defined.

## Versioning

- **No tool reports its version.** There are tags now, so "which fleet is this?"
  has an answer, and nothing prints it. The awkward part is not the flag but the
  fourteen ad-hoc argument parsers: several tools treat the first non-flag
  argument as a session name, so a bare `--version` has to be handled before
  that, uniformly, without changing any tool's existing exit codes.

- **`install` neither records nor reports what it linked.** It symlinks the
  working tree, so the installed version is whatever the checkout is now — which
  is right, and means a machine cannot answer "what did I install, and has it
  moved since?" without looking at git. Worth a line in `install --check`
  rather than a file, since a recorded copy of that is exactly the kind of state
  this repository refuses to keep.

- **`fleetsnap` adopts an unlabelled pane instead of excluding it.** Reported by
  the coordinator 2026-09-26 and verified: it is the one tool that does not use
  `fleet.panes.in_fleet`. It reads `@repo`, but only as a source for a session's
  NAME, and when that is absent it falls back to `claude agents`, then the
  transcript, then the pane title. So a pane on the same tmux server that was
  never part of the fleet is not dropped — it is named by fallback and reported as
  a member with no brief and no `[colors]` entry, on every run. `fleetupgrade`
  ignores the same pane correctly.

  **"Not ours" and "ours and broken" look identical to it, and it assumes the
  second.** The fix is the shape `fleetupgrade` already uses: apply `in_fleet`,
  exclude outsiders from the report, and collect them in an OUTSIDE list that is
  printed — because a fleet pane that lost its labels must not disappear in
  silence either.

  Care is warranted beyond the other four: `fleetsnap` writes the manifest
  `fleetrestore` rebuilds the fleet from, so excluding a pane wrongly removes a
  session from recovery. The naming fallback exists for a real reason (2026-09-18:
  a pane launched as a bare `claude` and named later has no label) and must keep
  working for panes that ARE ours.

  Also to correct when this lands: the v0.1.1 changelog entry says the membership
  label is one "`fleetsnap` already read", which overstates it. It read the label;
  it did not treat it as membership. Note the correction in the release that
  carries the fix rather than editing a published entry.

## Installation

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

  *Message-size feedback is the weaker case.* A `PreToolUse` hook on the peer-send
  tool that logs each send with its length and returns the size as context. It
  should not block: a hard cap makes senders split one thought across two
  messages, and the per-message wrapper is then charged twice, so splitting costs
  more than sending long.

  Proposed shape: a `hooks/` directory in this repository, and an `install` that
  **offers** to merge them, opt-in, merging and never replacing, with the same
  displaced-file discipline it already uses for symlinks. Opt-in is not timidity —
  that settings file is shared by everything the owner runs with Claude Code, not
  only the fleet.

  What would decide the second one: its only evidence so far comes from the single
  session that built it and knows it is being measured. That is the selection bias,
  and it needs sessions that did not build it before it ships as anything but
  optional. Ship the first; offer the second.

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

## fleetmail

- **Nothing builds the board.** `docs/source/tools/fleetmail.rst` sets out the
  rules a board must be built to — it renders *from* the repository and never
  back into it; it may carry subjects, senders, dates and delivery state; it may
  not carry message bodies or anything named in `[guard] refuse`. The rules are
  the hard half and they are written. Waiting on a second fleet to make it worth
  rendering.

## Visibility

- **`fleetwatch` could check that tmux's lock is real.** It reports who is
  attached; the operational control beside that is tmux's own `lock-after-time`
  with a `lock-command`. A `lock-command` naming a binary that is not installed
  fails toward *unlocked* and looks configured, which is this repository's
  signature failure. Both facts are derivable — `tmux show-options -g` and a
  `PATH` lookup — so the check is small. The judgement is whether a tool about
  fleet state should comment on the host's configuration at all.
