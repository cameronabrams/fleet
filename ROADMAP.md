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
